"""Decode and synchronize the observed extended ASIN AQUA Home LAN payload."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any

# The Node-RED flow reads offsets through data[115]. This is the minimum bytes needed
# to decode one payload, not a verified TCP frame length. A real capture is still
# needed to document the complete wire framing and any trailing bytes.
MIN_PAYLOAD_LENGTH = 116
FRAME_LENGTH = MIN_PAYLOAD_LENGTH  # Backward-compatible alias; not a wire-frame claim.
DEFAULT_MAX_CHLORINE = 20.0
MAX_BUFFER_SIZE = 16_384
HEX_DUMP_BYTES = 48

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


class InvalidFrameError(ValueError):
    """Raised when a candidate payload is structurally or semantically invalid."""


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


@dataclass(slots=True)
class CandidateEvent:
    """Compact parser event suitable for opt-in debug capture diagnostics."""

    accepted: bool
    offset: int
    reason: str
    candidate_hex: str
    detected_frame_length: int | None = None


class FrameBuffer:
    """Synchronize raw TCP bytes using validated payload starts and lookahead.

    The Node-RED export has no verified delimiter or extended-frame checksum. To
    avoid inventing a wire format, this scanner locates candidate starts using the
    tested fields and only emits a payload after the next validated start confirms
    its boundary. The final candidate remains buffered until more bytes arrive.
    """

    def __init__(
        self,
        decoder: AsekoProtocolDecoder | None = None,
        *,
        max_chlorine: float = DEFAULT_MAX_CHLORINE,
    ) -> None:
        self._decoder = decoder or AsekoProtocolDecoder(max_chlorine=max_chlorine)
        self._buffer = bytearray()
        self.events: list[CandidateEvent] = []
        self.detected_frame_length: int | None = None

    @property
    def pending_bytes(self) -> int:
        return len(self._buffer)

    def feed(self, chunk: bytes) -> list[DecodedData]:
        """Append a TCP chunk and return only synchronized, validated updates."""

        self.events = []
        self._buffer.extend(chunk)
        updates: list[DecodedData] = []
        while len(self._buffer) >= MIN_PAYLOAD_LENGTH:
            first_start = self._find_valid_start(0)
            if first_start is None:
                self._discard_unusable_prefix()
                break
            if first_start:
                self.events.append(
                    CandidateEvent(
                        False,
                        0,
                        f"discarded {first_start} leading unsynchronized byte(s)",
                        compact_hex(self._buffer[:first_start]),
                    )
                )
                del self._buffer[:first_start]

            next_start = self._find_valid_start(MIN_PAYLOAD_LENGTH)
            if next_start is None:
                break

            self.detected_frame_length = next_start
            candidate = bytes(self._buffer[:MIN_PAYLOAD_LENGTH])
            decoded = self._decoder.decode(candidate)
            decoded.raw_fields["detected_frame_length"] = next_start
            self.events.append(
                CandidateEvent(
                    True,
                    0,
                    "validated payload and next synchronized boundary",
                    compact_hex(self._buffer[:next_start]),
                    next_start,
                )
            )
            updates.append(decoded)
            del self._buffer[:next_start]
        return updates

    def _find_valid_start(self, start: int) -> int | None:
        last_start = len(self._buffer) - MIN_PAYLOAD_LENGTH
        for offset in range(start, last_start + 1):
            candidate = bytes(self._buffer[offset : offset + MIN_PAYLOAD_LENGTH])
            try:
                self._decoder.validate(candidate)
            except InvalidFrameError as err:
                # Keep captures bounded: offset zero explains loss of sync while a
                # discarded-prefix event summarizes the subsequent byte scan.
                if offset == start:
                    self.events.append(
                        CandidateEvent(False, offset, str(err), compact_hex(candidate))
                    )
            else:
                return offset
        return None

    def _discard_unusable_prefix(self) -> None:
        keep = MIN_PAYLOAD_LENGTH - 1
        if len(self._buffer) <= keep:
            return
        discard = len(self._buffer) - keep
        self.events.append(
            CandidateEvent(
                False,
                0,
                f"discarded {discard} byte(s) without a validated payload start",
                compact_hex(self._buffer[:discard]),
            )
        )
        del self._buffer[:discard]
        if len(self._buffer) > MAX_BUFFER_SIZE:
            del self._buffer[:-keep]


class AsekoProtocolDecoder:
    """Stateful decoder ported from the tested Node-RED function nodes."""

    def __init__(self, *, max_chlorine: float = DEFAULT_MAX_CHLORINE) -> None:
        self._max_chlorine = max_chlorine
        self._air_temperature: float | None = None
        self._water_temperature: float | None = None
        self._status = StatusState()

    def validate(self, frame: bytes) -> None:
        """Reject shifted or implausible candidates before publishing entities."""

        if len(frame) < MIN_PAYLOAD_LENGTH:
            raise InvalidFrameError(
                f"payload is too short: {len(frame)} < {MIN_PAYLOAD_LENGTH}"
            )
        self._validate_range("month", frame[7], 1, 12)
        self._validate_range("day", frame[8], 1, 31)
        self._validate_range("hour", frame[9], 0, 23)
        self._validate_range("minute", frame[10], 0, 59)
        self._validate_range("second", frame[11], 0, 59)
        self._validate_range("pH", self._word(frame, 14) / 100, 0, 14)
        self._validate_range(
            "chlorine", self._word(frame, 16) / 100, 0, self._max_chlorine
        )
        for name, hour_index, minute_index in (
            ("filter 1 start", 56, 57),
            ("filter 1 end", 58, 59),
            ("filter 2 start", 60, 61),
            ("filter 2 end", 62, 63),
            ("backwash start", 69, 70),
        ):
            self._validate_range(f"{name} hour", frame[hour_index], 0, 23)
            self._validate_range(f"{name} minute", frame[minute_index], 0, 59)

    def decode(self, frame: bytes) -> DecodedData:
        """Decode a validated candidate and update retained status state."""

        self.validate(frame)
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
        deviation_seconds = abs(
            (
                datetime.now().astimezone().replace(tzinfo=None) - device_datetime
            ).total_seconds()
        )
        sensors: dict[str, Any] = {
            "ph": self._word(data, 14) / 100,
            "chlorine": self._word(data, 16) / 100,
            "air_temperature": self._air_temperature,
            "water_temperature": self._water_temperature,
            "water_level": data[27] + 33,
            "water_level_probe": data[27],
            "system_date": device_datetime.strftime("%d.%m.%Y"),
            "system_time": device_datetime.strftime("%H:%M:%S"),
            "time_deviation": self._duration(deviation_seconds),
            "set_time_recommended": deviation_seconds > 300,
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
                "minimum_payload_length": MIN_PAYLOAD_LENGTH,
                "payload_hex": frame[:MIN_PAYLOAD_LENGTH].hex(),
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
    def _validate_range(name: str, value: float, low: float, high: float) -> None:
        if not low <= value <= high:
            raise InvalidFrameError(f"{name} {value} outside {low}..{high}")

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
    def _duration(seconds: float) -> str:
        seconds = int(seconds)
        return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"

    @staticmethod
    def _device_datetime(data: bytes) -> datetime:
        return datetime(data[6] + 2000, data[7], data[8], data[9], data[10], data[11])


def compact_hex(data: bytes | bytearray) -> str:
    """Return a bounded head/tail hex dump for debug logs and diagnostics."""

    raw = bytes(data)
    if len(raw) <= HEX_DUMP_BYTES:
        return raw.hex()
    half = HEX_DUMP_BYTES // 2
    return f"{raw[:half].hex()}...{raw[-half:].hex()}"
