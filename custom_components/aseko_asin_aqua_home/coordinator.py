"""Push coordinator and TCP server for ASEKO ASIN AQUA Home."""

from __future__ import annotations
import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from typing import Any
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change, async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from .backwash_tracker import BackwashTracker
from .const import UNAVAILABLE_AFTER
from .dosing_tracker import DosingTracker
from .forecast import ConsumptionForecast
from .protocol import CandidateEvent, DecodedData, FrameBuffer

_LOGGER = logging.getLogger(__name__)
_CAPTURE_LIMIT = 200
_CLOSE_TIMEOUT = 3.0
_CLOUD_CONNECT_TIMEOUT = 5.0


@dataclass
class GatewaySession:
    """Active gateway connection and its optional one-way cloud forwarding."""

    gateway_writer: asyncio.StreamWriter
    parser: FrameBuffer | None = None
    cloud_writer: asyncio.StreamWriter | None = None
    cloud_discard_task: asyncio.Task[None] | None = None
    session_task: asyncio.Task[None] | None = None
    closing: bool = False
    closed: bool = False
    cleanup_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    cloud_close_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class AsekoCoordinator(DataUpdateCoordinator[DecodedData]):
    """Receive local frames and push decoded updates to entities."""

    def __init__(
        self, hass: HomeAssistant, entry_id: str, options: dict[str, Any]
    ) -> None:
        super().__init__(hass, _LOGGER, name="ASEKO ASIN AQUA Home")
        self.options = options
        self.server: asyncio.AbstractServer | None = None
        self.last_valid_frame: datetime | None = None
        self.clients = 0
        self.capture_records: deque[dict[str, Any]] = deque(maxlen=_CAPTURE_LIMIT)
        self._availability_cancel = None
        self._midnight_cancel = None
        self._sessions: dict[asyncio.StreamWriter, GatewaySession] = {}
        self._forwarding_lock = asyncio.Lock()
        self._stopping = False
        self._stop_task: asyncio.Task[None] | None = None
        self.dosing_tracker = DosingTracker(hass, entry_id)
        self.backwash_tracker = BackwashTracker(hass, entry_id)
        self.forecast = ConsumptionForecast(hass)

    async def async_start(self) -> None:
        await self.dosing_tracker.async_load()
        await self.backwash_tracker.async_load()
        await self.forecast.async_load()
        await self._async_day_changed(datetime.now(timezone.utc))
        self.server = await asyncio.start_server(
            self._accept_client,
            self.options["listen_host"],
            self.options["listen_port"],
        )
        self._availability_cancel = async_track_time_interval(
            self.hass, self._refresh_availability, UNAVAILABLE_AFTER
        )
        self._midnight_cancel = async_track_time_change(
            self.hass, self._async_day_changed, hour=0, minute=0, second=0
        )
        _LOGGER.info(
            "Listening for ASIN AQUA Home on %s:%s",
            self.options["listen_host"],
            self.options["listen_port"],
        )

    async def async_stop(self, _event=None) -> None:
        """Share one cleanup between HA stop and unload; propagate caller cancellation."""
        self._stopping = True
        if self._stop_task is None:
            self._stop_task = asyncio.create_task(self._async_stop())
        # Cancellation of a caller must not cancel cleanup or be swallowed.
        await asyncio.shield(self._stop_task)

    async def _async_stop(self) -> None:
        if self._availability_cancel:
            self._availability_cancel()
            self._availability_cancel = None
        if self._midnight_cancel:
            self._midnight_cancel()
            self._midnight_cancel = None

        server = self.server
        if server is not None:
            server.close()

        # The synchronous accept callback registers sessions before yielding and
        # rejects new ones once stopping starts, so this snapshot cannot miss one.
        sessions = list(self._sessions.values())
        tasks = set()
        for session in sessions:
            session.gateway_writer.close()
            if session.cloud_writer is not None:
                session.cloud_writer.close()
            task = session.session_task
            if task is not None and not task.done():
                # Do not interrupt a handler already executing its finally block.
                if not session.closing:
                    task.cancel()
                tasks.add(task)
            tasks.add(asyncio.create_task(self._close_session(session)))

        if tasks:
            done, pending = await asyncio.wait(tasks, timeout=3 * _CLOSE_TIMEOUT)
            for task in done:
                if not task.cancelled() and task.exception() is not None:
                    _LOGGER.warning("ASEKO session cleanup failed: %s", task.exception())
            if pending:
                for session in sessions:
                    _abort_writer(session.gateway_writer)
                    _abort_writer(session.cloud_writer)
                for task in pending:
                    task.cancel()
                done, pending = await asyncio.wait(pending, timeout=_CLOSE_TIMEOUT)
                for task in done:
                    if not task.cancelled():
                        task.exception()
                if pending:
                    _LOGGER.warning("ASEKO shutdown: %d session tasks did not finish", len(pending))

        # Since Python 3.12 this also waits for accepted connections to close.
        if server is not None:
            try:
                await asyncio.wait_for(server.wait_closed(), timeout=_CLOSE_TIMEOUT)
            except asyncio.TimeoutError:
                _LOGGER.warning("ASEKO TCP server close timed out")
            self.server = None

        # Save after handlers stop mutating state, including their final frames.
        await self.dosing_tracker.async_save()
        await self.backwash_tracker.async_save_if_dirty()
        await self.forecast.async_save(force=True)
        self.forecast.break_observation()

    @callback
    def _accept_client(self, reader, writer) -> None:
        """Register accepted sockets synchronously, including during server close."""
        if self._stopping:
            writer.close()
            _abort_writer(writer)
            return
        session = self._register_session(writer)
        session.session_task = asyncio.create_task(self._handle_client(reader, writer, session))

    def _register_session(self, writer) -> GatewaySession:
        session = GatewaySession(gateway_writer=writer)
        self._sessions[writer] = session
        self.clients += 1
        return session

    async def _close_session(self, session: GatewaySession) -> None:
        """Serialize handler-finally and shutdown cleanup for each connection."""
        async with session.cleanup_lock:
            if session.closed:
                return
            session.closing = True
            try:
                await self._close_cloud_forwarding(session)
                await _close_writer_safely(session.gateway_writer)
            finally:
                _abort_writer(session.gateway_writer)
                _abort_writer(session.cloud_writer)
                self._sessions.pop(session.gateway_writer, None)
                self.clients = max(0, self.clients - 1)
                self.forecast.break_observation()
                session.closed = True

    async def _async_day_changed(self, now: datetime) -> None:
        """Publish the new local day's counters even without gateway traffic."""
        if self.dosing_tracker.advance_day(now):
            await self.dosing_tracker.async_save()
        self.forecast.advance_day(now)
        await self.forecast.async_save(force=True)
        self.async_update_listeners()

    @property
    def data_available(self) -> bool:
        return (
            self.last_valid_frame is not None
            and datetime.now(timezone.utc) - self.last_valid_frame <= UNAVAILABLE_AFTER
        )

    @callback
    def _refresh_availability(self, _now: datetime) -> None:
        self.async_update_listeners()

    def reconfigure_protocol_options(self) -> None:
        """Apply decoder-only options to active gateway parsers."""
        for session in self._sessions.values():
            if session.parser is not None:
                self._configure_parser(session.parser)

    def _new_parser(self) -> FrameBuffer:
        parser = FrameBuffer()
        self._configure_parser(parser)
        return parser

    def _configure_parser(self, parser: FrameBuffer) -> None:
        parser.configure(
            max_chlorine=self.options["max_chlorine"],
            water_level_offset=self.options["water_level_offset"],
            water_level_error_labels=self.options.get(
                "water_level_error_labels", False
            ),
            time_correction_threshold_minutes=self.options.get(
                "time_correction_threshold_minutes", 5
            ),
        )

    async def async_set_forwarding_enabled(self, enabled: bool) -> None:
        """Enable or disable one-way cloud forwarding for active sessions."""
        await self.async_reconfigure_cloud_forwarding(
            enabled=enabled,
            host=self.options["forward_host"],
            port=self.options["forward_port"],
        )

    async def async_reconfigure_cloud_forwarding(
        self,
        *,
        enabled: bool,
        host: str,
        port: int,
    ) -> None:
        """Apply cloud forwarding options without interrupting local gateway sessions."""
        async with self._forwarding_lock:
            if self._stopping:
                return
            self.options["forward_enabled"] = enabled
            self.options["forward_host"] = host
            self.options["forward_port"] = port

            sessions = list(self._sessions.values())
            for session in sessions:
                await self._close_cloud_forwarding(session)

            if not enabled:
                return

            for session in sessions:
                await self._open_cloud_forwarding(session)

    async def _open_cloud_forwarding(self, session: GatewaySession) -> None:
        """Open one-way cloud forwarding for a gateway session if possible."""
        if self._stopping or session.closing or session.cloud_writer is not None:
            return
        host = self.options["forward_host"]
        port = self.options["forward_port"]
        try:
            cloud_reader, cloud_writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=_CLOUD_CONNECT_TIMEOUT,
            )
        except (asyncio.TimeoutError, OSError, ConnectionError) as err:
            _LOGGER.warning(
                "Cloud forwarding connection to %s:%s failed or timed out: %s",
                host,
                port,
                err,
            )
            return
        if self._stopping or session.closing:
            await _close_writer_safely(cloud_writer)
            return
        session.cloud_writer = cloud_writer
        session.cloud_discard_task = asyncio.create_task(
            self._discard_cloud_responses(cloud_reader)
        )

    async def _close_cloud_forwarding(self, session: GatewaySession) -> None:
        """Close one-way cloud forwarding without touching the gateway writer."""
        async with session.cloud_close_lock:
            task = session.cloud_discard_task
            writer = session.cloud_writer
            session.cloud_discard_task = None
            session.cloud_writer = None
            if writer is not None:
                writer.close()
            try:
                if task is not None:
                    task.cancel()
                    # gather consumes the child's cancellation, not our own.
                    await asyncio.wait_for(
                        asyncio.gather(task, return_exceptions=True),
                        timeout=_CLOSE_TIMEOUT,
                    )
                await _close_writer_safely(writer)
            except asyncio.TimeoutError:
                _LOGGER.debug("Cloud response task close timed out")
            finally:
                _abort_writer(writer)

    async def _forward_chunk_to_cloud(
        self, session: GatewaySession, chunk: bytes
    ) -> None:
        """Forward a gateway chunk to the cloud without interrupting local handling."""
        cloud_writer = session.cloud_writer
        if cloud_writer is None:
            return
        try:
            cloud_writer.write(chunk)
            await cloud_writer.drain()  # controller -> cloud, unchanged
        except (ConnectionError, OSError) as err:
            _LOGGER.warning("Cloud forwarding write failed: %s", err)
            await self._close_cloud_forwarding(session)

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
        session: GatewaySession | None = None,
    ) -> None:
        if session is None:
            if self._stopping:
                writer.close()
                _abort_writer(writer)
                return
            session = self._register_session(writer)
            session.session_task = asyncio.current_task()
        _LOGGER.debug("Gateway connected from %s", writer.get_extra_info("peername"))
        try:
            if self.options["forward_enabled"]:
                await self._open_cloud_forwarding(session)
            parser = self._new_parser()
            session.parser = parser
            while chunk := await reader.read(4096):
                self._record_chunk(chunk, parser.pending_bytes)
                await self._forward_chunk_to_cloud(session, chunk)
                for decoded in parser.feed(chunk):
                    now = datetime.now(timezone.utc)
                    self.last_valid_frame = now
                    relay_transition = self.dosing_tracker.observe_relays(
                        decoded.relays, now
                    )
                    self.forecast.observe(decoded.relays, decoded.sensors, now)
                    backwash_event = self.backwash_tracker.observe_relay(
                        bool(decoded.relays.get("backwash", False)), now
                    )
                    self.async_set_updated_data(decoded)
                    if relay_transition:
                        await self.dosing_tracker.async_save()
                    else:
                        await self.dosing_tracker.async_maybe_save(now)
                    await self.forecast.async_save(now=now)
                    if backwash_event:
                        await self.backwash_tracker.async_save()
                        self.async_update_listeners()
                    else:
                        await self.backwash_tracker.async_save_if_dirty()
                self._record_parser_events(parser)
                if self.options["protocol_debug"]:
                    _LOGGER.debug("ASEKO pending buffer=%d", parser.pending_bytes)
        except ConnectionError as err:
            _LOGGER.debug("Gateway disconnected: %s", err)
        finally:
            await self._close_session(session)

    def _record_chunk(self, chunk: bytes, pending_before: int) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        first, last = chunk[:8].hex(), chunk[-8:].hex()
        if self.options["protocol_debug"]:
            _LOGGER.debug(
                "ASEKO TCP chunk length=%d first=%s last=%s pending_before=%d",
                len(chunk),
                first,
                last,
                pending_before,
            )
        if self.options["capture_enabled"]:
            self.capture_records.append(
                {
                    "timestamp": timestamp,
                    "type": "tcp_chunk",
                    "chunk_length": len(chunk),
                    "chunk_hex": chunk.hex(),
                    "first_hex": first,
                    "last_hex": last,
                    "pending_before": pending_before,
                }
            )

    def _record_parser_events(self, parser: FrameBuffer) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        for event in parser.events:
            if self.options["protocol_debug"]:
                _LOGGER.debug(
                    (
                        "ASEKO payload candidate status=%s accepted=%s offset=%d "
                        "discarded=%d pending=%d reason=%s hex=%s"
                    ),
                    event.status,
                    event.accepted,
                    event.offset,
                    event.discarded_bytes,
                    event.pending_bytes,
                    event.reason,
                    event.candidate_hex,
                )
            if self.options["capture_enabled"]:
                self.capture_records.append(self._capture_event(timestamp, event))

    @staticmethod
    def _capture_event(timestamp: str, event: CandidateEvent) -> dict[str, Any]:
        return {
            "timestamp": timestamp,
            "type": "payload_candidate",
            "accepted": event.accepted,
            "status": event.status,
            "offset": event.offset,
            "reason": event.reason,
            "candidate_hex": event.candidate_hex,
            "discarded_bytes": event.discarded_bytes,
            "pending_bytes": event.pending_bytes,
            "aligned_frame_hex": event.aligned_frame_hex,
            "decoded_payload_hex": event.decoded_payload_hex,
        }

    @staticmethod
    async def _discard_cloud_responses(reader: asyncio.StreamReader) -> None:
        """Drain cloud responses without relaying them to the local gateway."""
        try:
            while chunk := await reader.read(4096):
                _LOGGER.debug("Discarded %d byte ASEKO cloud response", len(chunk))
        except (ConnectionError, OSError):
            pass


async def _close_writer_safely(
    writer: asyncio.StreamWriter | None,
    timeout: float | None = None,
) -> None:
    """Close a stream writer without allowing shutdown to hang indefinitely."""
    if writer is None:
        return
    try:
        writer.close()
        await asyncio.wait_for(
            writer.wait_closed(), timeout=_CLOSE_TIMEOUT if timeout is None else timeout
        )
    except (ConnectionError, OSError, asyncio.TimeoutError) as err:
        _abort_writer(writer)
        _LOGGER.debug("TCP writer close failed or timed out: %s", err)
    except asyncio.CancelledError:
        _abort_writer(writer)
        raise


def _abort_writer(writer: asyncio.StreamWriter | None) -> None:
    """Release transports even if graceful close is blocked by buffered writes."""
    transport = getattr(writer, "transport", None)
    if transport is not None:
        transport.abort()
