"""Push coordinator and TCP server for ASEKO ASIN AQUA Home."""

from __future__ import annotations
import asyncio
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from typing import Any
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from .backwash_tracker import BackwashTracker
from .const import UNAVAILABLE_AFTER
from .dosing_tracker import DosingTracker
from .protocol import CandidateEvent, DecodedData, FrameBuffer

_LOGGER = logging.getLogger(__name__)
_CAPTURE_LIMIT = 200


@dataclass
class GatewaySession:
    """Active gateway connection and its optional one-way cloud forwarding."""

    gateway_writer: asyncio.StreamWriter
    cloud_writer: asyncio.StreamWriter | None = None
    cloud_discard_task: asyncio.Task[None] | None = None


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
        self._sessions: dict[asyncio.StreamWriter, GatewaySession] = {}
        self._forwarding_lock = asyncio.Lock()
        self.dosing_tracker = DosingTracker(hass, entry_id)
        self.backwash_tracker = BackwashTracker(hass, entry_id)

    async def async_start(self) -> None:
        await self.dosing_tracker.async_load()
        await self.backwash_tracker.async_load()
        self.server = await asyncio.start_server(
            self._handle_client,
            self.options["listen_host"],
            self.options["listen_port"],
        )
        self._availability_cancel = async_track_time_interval(
            self.hass, self._refresh_availability, UNAVAILABLE_AFTER
        )
        _LOGGER.info(
            "Listening for ASIN AQUA Home on %s:%s",
            self.options["listen_host"],
            self.options["listen_port"],
        )

    async def async_stop(self) -> None:
        if self._availability_cancel:
            self._availability_cancel()
            self._availability_cancel = None
        await self.dosing_tracker.async_save()
        await self.backwash_tracker.async_save_if_dirty()
        for session in list(self._sessions.values()):
            await self._close_cloud_forwarding(session)
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self.server = None

    @property
    def data_available(self) -> bool:
        return (
            self.last_valid_frame is not None
            and datetime.now(timezone.utc) - self.last_valid_frame <= UNAVAILABLE_AFTER
        )

    @callback
    def _refresh_availability(self, _now: datetime) -> None:
        self.async_update_listeners()

    async def async_set_forwarding_enabled(self, enabled: bool) -> None:
        """Enable or disable one-way cloud forwarding for active sessions."""
        async with self._forwarding_lock:
            self.options["forward_enabled"] = enabled
            sessions = list(self._sessions.values())
            if enabled:
                for session in sessions:
                    if session.cloud_writer is None:
                        await self._open_cloud_forwarding(session)
            else:
                for session in sessions:
                    await self._close_cloud_forwarding(session)

    async def _open_cloud_forwarding(self, session: GatewaySession) -> None:
        """Open one-way cloud forwarding for a gateway session if possible."""
        if session.cloud_writer is not None:
            return
        try:
            cloud_reader, cloud_writer = await asyncio.open_connection(
                self.options["forward_host"], self.options["forward_port"]
            )
        except OSError as err:
            _LOGGER.warning("Cloud forwarding connection failed: %s", err)
            return
        session.cloud_writer = cloud_writer
        session.cloud_discard_task = asyncio.create_task(
            self._discard_cloud_responses(cloud_reader)
        )

    async def _close_cloud_forwarding(self, session: GatewaySession) -> None:
        """Close one-way cloud forwarding without touching the gateway writer."""
        if session.cloud_discard_task:
            session.cloud_discard_task.cancel()
            try:
                await session.cloud_discard_task
            except asyncio.CancelledError:
                pass
            session.cloud_discard_task = None
        if session.cloud_writer:
            session.cloud_writer.close()
            try:
                await session.cloud_writer.wait_closed()
            except ConnectionError as err:
                _LOGGER.debug("Cloud forwarding close failed: %s", err)
            session.cloud_writer = None

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
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self.clients += 1
        session = GatewaySession(gateway_writer=writer)
        self._sessions[writer] = session
        _LOGGER.debug("Gateway connected from %s", writer.get_extra_info("peername"))
        try:
            if self.options["forward_enabled"]:
                await self._open_cloud_forwarding(session)
            parser = FrameBuffer(
                max_chlorine=self.options["max_chlorine"],
                water_level_offset=self.options["water_level_offset"],
            )
            while chunk := await reader.read(4096):
                self._record_chunk(chunk, parser.pending_bytes)
                await self._forward_chunk_to_cloud(session, chunk)
                for decoded in parser.feed(chunk):
                    now = datetime.now(timezone.utc)
                    self.last_valid_frame = now
                    relay_transition = self.dosing_tracker.observe_relays(
                        decoded.relays, now
                    )
                    backwash_event = self.backwash_tracker.observe_relay(
                        bool(decoded.relays.get("backwash", False)), now
                    )
                    self.async_set_updated_data(decoded)
                    if relay_transition:
                        await self.dosing_tracker.async_save()
                    else:
                        await self.dosing_tracker.async_maybe_save(now)
                    if backwash_event:
                        await self.backwash_tracker.async_save()
                        self.async_update_listeners()
                    else:
                        await self.backwash_tracker.async_save_if_dirty()
                self._record_parser_events(parser)
                if self.options["protocol_debug"]:
                    _LOGGER.debug("ASEKO pending buffer=%d", parser.pending_bytes)
        except (ConnectionError, asyncio.CancelledError) as err:
            _LOGGER.debug("Gateway disconnected: %s", err)
        finally:
            self.clients -= 1
            self._sessions.pop(writer, None)
            await self._close_cloud_forwarding(session)
            writer.close()
            await writer.wait_closed()

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
                    "ASEKO payload candidate accepted=%s offset=%d reason=%s hex=%s",
                    event.accepted,
                    event.offset,
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
            "offset": event.offset,
            "reason": event.reason,
            "candidate_hex": event.candidate_hex,
        }

    @staticmethod
    async def _discard_cloud_responses(reader: asyncio.StreamReader) -> None:
        """Drain cloud responses without relaying them to the local gateway."""
        try:
            while chunk := await reader.read(4096):
                _LOGGER.debug("Discarded %d byte ASEKO cloud response", len(chunk))
        except (ConnectionError, asyncio.CancelledError):
            pass
