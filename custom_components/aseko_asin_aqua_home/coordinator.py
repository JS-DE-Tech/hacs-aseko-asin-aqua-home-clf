"""Push coordinator and TCP server for ASEKO ASIN AQUA Home."""

from __future__ import annotations
import asyncio
from collections import deque
from datetime import datetime, timezone
import logging
from typing import Any
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from .const import UNAVAILABLE_AFTER
from .protocol import CandidateEvent, DecodedData, FrameBuffer

_LOGGER = logging.getLogger(__name__)
_CAPTURE_LIMIT = 200


class AsekoCoordinator(DataUpdateCoordinator[DecodedData]):
    """Receive local frames and push decoded updates to entities."""

    def __init__(self, hass: HomeAssistant, options: dict[str, Any]) -> None:
        super().__init__(hass, _LOGGER, name="ASEKO ASIN AQUA Home")
        self.options = options
        self.server: asyncio.AbstractServer | None = None
        self.last_valid_frame: datetime | None = None
        self.clients = 0
        self.capture_records: deque[dict[str, Any]] = deque(maxlen=_CAPTURE_LIMIT)
        self._availability_cancel = None

    async def async_start(self) -> None:
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

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self.clients += 1
        _LOGGER.debug("Gateway connected from %s", writer.get_extra_info("peername"))
        cloud_writer: asyncio.StreamWriter | None = None
        cloud_discard_task: asyncio.Task[None] | None = None
        try:
            if self.options["forward_enabled"]:
                try:
                    cloud_reader, cloud_writer = await asyncio.open_connection(
                        self.options["forward_host"], self.options["forward_port"]
                    )
                    cloud_discard_task = asyncio.create_task(
                        self._discard_cloud_responses(cloud_reader)
                    )
                except OSError as err:
                    _LOGGER.warning("Cloud forwarding connection failed: %s", err)
            parser = FrameBuffer(
                max_chlorine=self.options["max_chlorine"],
                water_level_offset=self.options["water_level_offset"],
            )
            while chunk := await reader.read(4096):
                self._record_chunk(chunk, parser.pending_bytes)
                if cloud_writer:
                    cloud_writer.write(chunk)
                    await cloud_writer.drain()  # controller -> cloud, unchanged
                for decoded in parser.feed(chunk):
                    self.last_valid_frame = datetime.now(timezone.utc)
                    self.async_set_updated_data(decoded)
                self._record_parser_events(parser)
                if self.options["protocol_debug"]:
                    _LOGGER.debug("ASEKO pending buffer=%d", parser.pending_bytes)
        except (ConnectionError, asyncio.CancelledError) as err:
            _LOGGER.debug("Gateway disconnected: %s", err)
        finally:
            self.clients -= 1
            if cloud_discard_task:
                cloud_discard_task.cancel()
            if cloud_writer:
                cloud_writer.close()
                await cloud_writer.wait_closed()
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
