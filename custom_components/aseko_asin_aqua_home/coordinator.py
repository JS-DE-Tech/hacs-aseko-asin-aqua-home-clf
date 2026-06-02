"""Push coordinator and TCP server for ASEKO ASIN AQUA Home."""

from __future__ import annotations
import asyncio
from datetime import datetime, timezone
import logging
from typing import Any
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from .const import UNAVAILABLE_AFTER
from .protocol import AsekoProtocolDecoder, DecodedData, FrameBuffer

_LOGGER = logging.getLogger(__name__)


class AsekoCoordinator(DataUpdateCoordinator[DecodedData]):
    """Receive local frames and push decoded updates to entities."""

    def __init__(self, hass: HomeAssistant, options: dict[str, Any]) -> None:
        super().__init__(hass, _LOGGER, name="ASEKO ASIN AQUA Home")
        self.options = options
        self.server: asyncio.AbstractServer | None = None
        self.last_valid_frame: datetime | None = None
        self.clients = 0
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
        peer = writer.get_extra_info("peername")
        _LOGGER.debug("Gateway connected from %s", peer)
        cloud_reader = None
        cloud_writer = None
        cloud_task = None
        try:
            if self.options["forward_enabled"]:
                try:
                    cloud_reader, cloud_writer = await asyncio.open_connection(
                        self.options["forward_host"], self.options["forward_port"]
                    )
                    cloud_task = asyncio.create_task(
                        self._relay_cloud(cloud_reader, writer)
                    )
                except OSError as err:
                    _LOGGER.warning("Cloud forwarding connection failed: %s", err)
            buffer = FrameBuffer()
            decoder = AsekoProtocolDecoder()
            while chunk := await reader.read(4096):
                if cloud_writer:
                    cloud_writer.write(chunk)
                    await cloud_writer.drain()  # original bytes unchanged
                for frame in buffer.feed(chunk):
                    try:
                        decoded = decoder.decode(frame)
                    except ValueError as err:
                        _LOGGER.debug("Rejected malformed frame: %s", err)
                    else:
                        self.last_valid_frame = datetime.now(timezone.utc)
                        self.async_set_updated_data(decoded)
        except (ConnectionError, asyncio.CancelledError) as err:
            _LOGGER.debug("Gateway disconnected: %s", err)
        finally:
            self.clients -= 1
            if cloud_task:
                cloud_task.cancel()
            if cloud_writer:
                cloud_writer.close()
                await cloud_writer.wait_closed()
            writer.close()
            await writer.wait_closed()

    @staticmethod
    async def _relay_cloud(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            while chunk := await reader.read(4096):
                writer.write(chunk)
                await writer.drain()
        except (ConnectionError, asyncio.CancelledError):
            pass
