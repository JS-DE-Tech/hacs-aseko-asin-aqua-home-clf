"""Decode the tested extended ASIN AQUA Home LAN payload."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any

FRAME_LENGTH = 116  # Tested flow indexes 0..115. Confirm framing with more captures.

ERROR_NAMES = (
    "hour_dosing_exceeded",
    "time_correction",
    "no_probe_flow",
    "buffer_tank_empty",
    "buffer_tank_overflow",
    "low_filling_speed",
    "ph_doses_without_change",
    "chlorine_doses_without_change",
)
RELAY_NAMES = (
    "backwash",
    "filling",
    "heating",
    "filtration",
    "algicide",
    "flocculation",
    "chlorine",
    "ph_minus",
)


@dataclass(slots=True)
class StatusState:
    """State retained across special or zero status frames, matching Node-RED."""

    raw: int = 0
    filtration: bool = False
    standby: bool = False
    heating: bool = False
    open_menu: bool = False


@dataclass(slots=True)
class DecodedData:
    """Decoded controller update."""

    sensors: dict[str, Any]
    errors: dict[str, bool]
    relays: dict[str, bool]
    status: StatusState
    raw_fields: dict[str, Any] = field(default_factory=dict)


class FrameBuffer:
    """Split TCP stream input into tested fixed-size extended frames."""

    def __init__(self, frame_length: int = FRAME_LENGTH) -> None:
        self._frame_length = frame_length
        self._buffer = bytearray()

    @property
    def pending_bytes(self) -> int:
        return len(self._buffer)

    def feed(self, chunk: bytes) -> list[bytes]:
        self._buffer.extend(chunk)
        frames: list[bytes] = []
        while len(self._buffer) >= self._frame_length:
            frames.append(bytes(self._buffer[: self._frame_length]))
            del self._buffer[: self._frame_length]
        return frames


class AsekoProtocolDecoder:
    """Stateful decoder ported from the tested Node-RED function nodes."""

    def __init__(self) -> None:
        self._air_temperature: float | None = None
        self._water_temperature: float | None = None
        self._status = StatusState()

    def decode(self, frame: bytes) -> DecodedData:
        if len(frame) < FRAME_LENGTH:
            raise ValueError(
                f"ASIN AQUA Home frame is too short: {len(frame)} < {FRAME_LENGTH}"
            )
        data = frame
        air_raw = self._decode_air_temperature(data[23], data[24])
        water_raw = self._word(data, 25) / 10
        self._air_temperature = self._fallback(air_raw, -30, 50, self._air_temperature)
        self._water_temperature = self._fallback(
            water_raw, -5, 45, self._water_temperature
        )
        error_byte, relay_byte, byte24 = data[13], data[29], data[25]
        errors = {
            name: bool(error_byte & (1 << bit)) for bit, name in enumerate(ERROR_NAMES)
        }
        relays = {
            name: bool(relay_byte & (1 << bit)) for bit, name in enumerate(RELAY_NAMES)
        }
        self._update_status(data[78])
        device_datetime = self._device_datetime(data)
        deviation_seconds = (
            abs(
                (
                    datetime.now().astimezone().replace(tzinfo=None) - device_datetime
                ).total_seconds()
            )
            if device_datetime
            else None
        )
        sensors: dict[str, Any] = {
            "ph": self._word(data, 14) / 100,
            "chlorine": self._word(data, 16) / 100,
            "air_temperature": self._air_temperature,
            "water_temperature": self._water_temperature,
            "water_level": data[27] + 33,
            "water_level_probe": data[27],
            "system_date": device_datetime.strftime("%d.%m.%Y")
            if device_datetime
            else None,
            "system_time": device_datetime.strftime("%H:%M:%S")
            if device_datetime
            else None,
            "time_deviation": self._duration(deviation_seconds),
            "set_time_recommended": deviation_seconds is not None
            and deviation_seconds > 300,
            "ph_target": data[52] / 10,
            "chlorine_target": data[53] / 10,
            "flocculation_dose": data[54],
            "water_temperature_target": data[55],
            "filter_1_start": self._time(data[56], data[57]),
            "filter_1_end": self._time(data[58], data[59]),
            "filter_2_start": self._time(data[60], data[61]),
            "filter_2_end": self._time(data[62], data[63]),
            "backwash_interval_days": data[68],
            "backwash_start": self._time(data[69], data[70]),
            "algicide_dose": data[72],
            "filling_time_limit": self._word(data, 76) / 60,
            "pool_volume": self._word(data, 92),
            "water_level_low": data[102],
            "refill_on": data[103],
            "refill_off": data[104],
            "water_level_high": data[105],
            "dosing_delay": self._word(data, 106) / 60,
            "startup_delay": self._word(data, 109) / 60,
            "concentration": data[111],
            "ph_minus_concentration": data[112],
            "max_chlorine_doses": data[114],
            "max_ph_doses": data[115],
            "error_byte": error_byte,
            "error_byte_binary": f"{error_byte:08b}",
            "relay_byte": relay_byte,
            "relay_byte_binary": f"{relay_byte:08b}",
            "byte24": byte24,
            "byte24_binary": f"{byte24:08b}",
            "raw_status": data[78],
        }
        # byte24 overlaps the tested water-temperature high byte. Its deeper meaning is
        # not verified; retain it unchanged for diagnostics until captures clarify it.
        return DecodedData(
            sensors,
            errors,
            relays,
            replace(self._status),
            {
                "frame_length": len(frame),
                "frame_hex": frame.hex(),
                "error_byte": error_byte,
                "relay_byte": relay_byte,
                "byte24": byte24,
                "status_byte": data[78],
            },
        )

    def _update_status(self, current: int) -> None:
        if current == 0:
            return
        status = self._status
        if current == 40:
            status.open_menu = True
        else:
            if current in {1, 17, 34, 98, 129, 130, 131, 145, 162, 178}:
                status.filtration = True
            elif current in {226, 64}:
                status.filtration = False
            status.heating = current in {130, 131, 162, 178}
            if current in {1, 17, 64, 129, 145}:
                status.standby = True
            elif current not in {64, 1}:
                status.standby = False
            status.open_menu = False
        status.raw = current

    @staticmethod
    def _word(data: bytes, index: int) -> int:
        return data[index] * 256 + data[index + 1]

    @staticmethod
    def _decode_air_temperature(high: int, low: int) -> float:
        return (low - 256) / 10 if high == 255 else (high * 256 + low) / 10

    @staticmethod
    def _fallback(
        value: float, low: float, high: float, previous: float | None
    ) -> float | None:
        return value if low <= value <= high else previous

    @staticmethod
    def _time(hour: int, minute: int) -> str:
        return f"{hour:02d}:{minute:02d}"

    @staticmethod
    def _duration(seconds: float | None) -> str | None:
        if seconds is None:
            return None
        seconds = int(seconds)
        return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"

    @staticmethod
    def _device_datetime(data: bytes) -> datetime | None:
        try:
            return datetime(
                data[6] + 2000, data[7], data[8], data[9], data[10], data[11]
            )
        except ValueError:
            return None
