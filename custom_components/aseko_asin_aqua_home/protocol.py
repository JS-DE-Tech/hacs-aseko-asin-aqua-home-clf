"""Decode and synchronize the observed extended ASIN AQUA Home LAN payload."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any

# Firmware-v7 binary traffic on port 47524 is framed as 120-byte wire frames.
# The local decoder currently maps bytes 0..115 only; bytes 116..119 remain
# preserved for diagnostics but intentionally undecoded.
BINARY_WIRE_FRAME_LENGTH = 120
MIN_PAYLOAD_LENGTH = 116
FRAME_LENGTH = MIN_PAYLOAD_LENGTH  # Backward-compatible alias; not a wire-frame claim.
BLOCK_SIZE = 40
FRAME_HEADER_LENGTH = 4
BLOCK_ID_OFFSET = 5
EXPECTED_BLOCK_IDS = (1, 3, 2)
DEFAULT_MAX_CHLORINE = 20.0
DEFAULT_WATER_LEVEL_OFFSET = 33
DEFAULT_TIME_CORRECTION_THRESHOLD_MINUTES = 5
MAX_BUFFER_SIZE = 16_384
HEX_DUMP_BYTES = 48
FILTRATION_NONSTOP_24H_VALUES = {0x43, 0x4B}
FILTRATION_TIMER_VALUES = {0x53, 0x5B}

ERROR_BITS = (
    ("hour_dosing_exceeded", 13, 0, "Stundendosierung überschritten"),
    ("time_correction", 13, 1, "Zeitkorrektur"),
    ("no_probe_flow", 13, 2, "Kein Durchfluss an den Sonden"),
    ("buffer_tank_empty", 13, 3, "Pufferbehälter leer"),
    ("buffer_tank_overflow", 13, 4, "Pufferbehälter übergelaufen"),
    ("low_filling_speed", 13, 5, "Nachfüllgeschwindigkeit zu gering"),
    ("ph_doses_without_change", 13, 6, "pH-Dosierungen ohne Änderung"),
    (
        "chlorine_doses_without_change",
        13,
        7,
        "Chlordosierungen ohne Änderung",
    ),
    ("rapid_ph_change", 12, 2, "Zu schnelle pH-Wert-Änderung"),
)
ERROR_NAMES = tuple(key for key, _, _, _ in ERROR_BITS)
ERROR_STATUS_ORDER = (
    "rapid_ph_change",
    "chlorine_doses_without_change",
    "no_probe_flow",
    "low_filling_speed",
    "ph_doses_without_change",
    "buffer_tank_empty",
    "buffer_tank_overflow",
    "hour_dosing_exceeded",
    "time_correction",
)
ERROR_STATUS_MESSAGES = {key: message for key, _, _, message in ERROR_BITS}
WATER_LEVEL_ERROR_STATUS_MESSAGES = {
    **ERROR_STATUS_MESSAGES,
    "buffer_tank_empty": "Wasserstand zu niedrig",
    "buffer_tank_overflow": "Wasserstand zu hoch",
}
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
    nonstop_24h: bool = False
    timer: bool = False


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
    status: str = "accepted"
    pending_bytes: int = 0
    discarded_bytes: int = 0
    aligned_frame_hex: str | None = None
    decoded_payload_hex: str | None = None


class FrameBuffer:
    """Synchronize TCP bytes into firmware-v7 binary wire frames.

    The wire protocol uses three 40-byte blocks with matching four-byte headers and
    block IDs 1, 3, and 2. The decoder only maps the first 116 bytes, so frame
    synchronization and payload decoding deliberately use separate lengths.
    """

    def __init__(
        self,
        decoder: AsekoProtocolDecoder | None = None,
        *,
        max_chlorine: float = DEFAULT_MAX_CHLORINE,
        water_level_offset: int = DEFAULT_WATER_LEVEL_OFFSET,
        water_level_error_labels: bool = False,
        time_correction_threshold_minutes: int = DEFAULT_TIME_CORRECTION_THRESHOLD_MINUTES,
    ) -> None:
        self._decoder = decoder or AsekoProtocolDecoder(
            max_chlorine=max_chlorine,
            water_level_offset=water_level_offset,
            water_level_error_labels=water_level_error_labels,
            time_correction_threshold_minutes=time_correction_threshold_minutes,
        )
        self._buffer = bytearray()
        self.events: list[CandidateEvent] = []

    @property
    def pending_bytes(self) -> int:
        return len(self._buffer)

    def feed(self, chunk: bytes) -> list[DecodedData]:
        """Append a TCP chunk and return only synchronized, validated updates."""
        self.events = []
        self._buffer.extend(chunk)
        updates: list[DecodedData] = []
        while len(self._buffer) >= FRAME_HEADER_LENGTH + BLOCK_ID_OFFSET + 1:
            start = self._find_possible_start()
            if start is None:
                self._discard_unusable_prefix()
                break
            if start:
                self.events.append(
                    CandidateEvent(
                        False,
                        0,
                        f"discarded {start} leading unsynchronized byte(s)",
                        compact_hex(self._buffer[:start]),
                        "discarded",
                        len(self._buffer) - start,
                        start,
                    )
                )
                del self._buffer[:start]
            if len(self._buffer) < BINARY_WIRE_FRAME_LENGTH:
                self.events.append(
                    CandidateEvent(
                        False,
                        0,
                        (
                            "possible frame start retained until complete "
                            f"120-byte wire frame is available"
                        ),
                        compact_hex(self._buffer),
                        "incomplete",
                        len(self._buffer),
                    )
                )
                break

            wire_frame = bytes(self._buffer[:BINARY_WIRE_FRAME_LENGTH])
            payload = wire_frame[:MIN_PAYLOAD_LENGTH]
            try:
                self._validate_wire_frame(wire_frame)
                self._decoder.validate(payload)
            except InvalidFrameError as err:
                self.events.append(
                    CandidateEvent(
                        False,
                        0,
                        str(err),
                        compact_hex(wire_frame),
                        "rejected",
                        len(self._buffer),
                    )
                )
                del self._buffer[:1]
                continue

            decoded = self._decoder.decode(payload)
            aligned_hex = wire_frame.hex()
            payload_hex = payload.hex()
            decoded.raw_fields["binary_wire_frame_length"] = BINARY_WIRE_FRAME_LENGTH
            decoded.raw_fields["wire_frame_hex"] = aligned_hex
            decoded.raw_fields["decoded_payload_hex"] = payload_hex
            decoded.raw_fields["undecoded_tail_hex"] = wire_frame[
                MIN_PAYLOAD_LENGTH:BINARY_WIRE_FRAME_LENGTH
            ].hex()
            self.events.append(
                CandidateEvent(
                    True,
                    0,
                    "validated 120-byte binary wire frame",
                    compact_hex(wire_frame),
                    "accepted",
                    len(self._buffer) - BINARY_WIRE_FRAME_LENGTH,
                    0,
                    aligned_hex,
                    payload_hex,
                )
            )
            updates.append(decoded)
            del self._buffer[:BINARY_WIRE_FRAME_LENGTH]
        return updates

    def _find_possible_start(self) -> int | None:
        last_start = len(self._buffer) - (FRAME_HEADER_LENGTH + BLOCK_ID_OFFSET + 1)
        for offset in range(last_start + 1):
            rejection_reason = self._available_structure_error(offset)
            if rejection_reason is None:
                return offset
            if offset == 0:
                candidate = self._buffer[
                    offset : offset + min(BINARY_WIRE_FRAME_LENGTH, len(self._buffer))
                ]
                self.events.append(
                    CandidateEvent(
                        False,
                        offset,
                        rejection_reason,
                        compact_hex(candidate),
                        "rejected",
                        len(self._buffer),
                    )
                )
        return None

    def _discard_unusable_prefix(self) -> None:
        keep = FRAME_HEADER_LENGTH + BLOCK_ID_OFFSET
        discard = max(0, len(self._buffer) - keep)
        if discard:
            self.events.append(
                CandidateEvent(
                    False,
                    0,
                    f"discarded {discard} byte(s) without a validated payload start",
                    compact_hex(self._buffer[:discard]),
                    "discarded",
                    len(self._buffer) - discard,
                    discard,
                )
            )
            del self._buffer[:discard]
        if len(self._buffer) > MAX_BUFFER_SIZE:
            del self._buffer[:-keep]

    def _available_structure_error(self, offset: int) -> str | None:
        remaining = len(self._buffer) - offset
        if remaining < FRAME_HEADER_LENGTH + BLOCK_ID_OFFSET + 1:
            return "not enough bytes to test binary frame structure"
        header = bytes(self._buffer[offset : offset + FRAME_HEADER_LENGTH])
        for block_index, expected_id in enumerate(EXPECTED_BLOCK_IDS):
            block_start = block_index * BLOCK_SIZE
            header_start = offset + block_start
            id_index = offset + block_start + BLOCK_ID_OFFSET
            if remaining >= block_start + 1:
                available_header = min(
                    FRAME_HEADER_LENGTH, remaining - block_start
                )
                if available_header > 0:
                    observed = bytes(
                        self._buffer[header_start : header_start + available_header]
                    )
                    if observed != header[:available_header]:
                        return (
                            "repeated block header mismatch at candidate offset "
                            f"{offset}, relative offset {block_start}"
                        )
            if remaining > block_start + BLOCK_ID_OFFSET:
                if self._buffer[id_index] != expected_id:
                    return (
                        "block id mismatch at candidate offset "
                        f"{offset}, relative offset {block_start + BLOCK_ID_OFFSET}: "
                        f"{self._buffer[id_index]} != {expected_id}"
                    )
        return None

    @staticmethod
    def _validate_wire_frame(frame: bytes) -> None:
        if len(frame) < BINARY_WIRE_FRAME_LENGTH:
            raise InvalidFrameError(
                "binary wire frame is too short: "
                f"{len(frame)} < {BINARY_WIRE_FRAME_LENGTH}"
            )
        header = frame[:FRAME_HEADER_LENGTH]
        for block_index, expected_id in enumerate(EXPECTED_BLOCK_IDS):
            block_start = block_index * BLOCK_SIZE
            observed_header = frame[
                block_start : block_start + FRAME_HEADER_LENGTH
            ]
            if observed_header != header:
                raise InvalidFrameError(
                    "repeated block header mismatch at offset "
                    f"{block_start}: {observed_header.hex()} != {header.hex()}"
                )
            observed_id = frame[block_start + BLOCK_ID_OFFSET]
            if observed_id != expected_id:
                raise InvalidFrameError(
                    "block id mismatch at offset "
                    f"{block_start + BLOCK_ID_OFFSET}: "
                    f"{observed_id} != {expected_id}"
                )


class AsekoProtocolDecoder:
    """Stateful decoder ported from the tested Node-RED function nodes."""

    def __init__(
        self,
        *,
        max_chlorine: float = DEFAULT_MAX_CHLORINE,
        water_level_offset: int = DEFAULT_WATER_LEVEL_OFFSET,
        water_level_error_labels: bool = False,
        time_correction_threshold_minutes: int = DEFAULT_TIME_CORRECTION_THRESHOLD_MINUTES,
    ) -> None:
        self._max_chlorine = max_chlorine
        self._water_level_offset = water_level_offset
        self._water_level_error_labels = water_level_error_labels
        self._time_correction_threshold_seconds = (
            time_correction_threshold_minutes * 60
        )
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
        # datetime catches impossible combinations such as 31 February.
        self._device_datetime(frame)
        current_year = datetime.now().year
        controller_year = frame[6] + 2000
        self._validate_range(
            "controller year", controller_year, current_year - 1, current_year + 1
        )
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
        warning_byte, error_byte, relay_byte, byte24 = (
            data[12],
            data[13],
            data[29],
            data[25],
        )
        relays = {
            name: bool(relay_byte & (1 << bit)) for bit, name in enumerate(RELAY_NAMES)
        }
        self._update_status(data[78])
        self._update_filtration_mode(data)
        device_datetime = self._device_datetime(data)
        deviation_seconds = abs(
            (
                datetime.now().astimezone().replace(tzinfo=None) - device_datetime
            ).total_seconds()
        )
        time_correction_recommended = (
            deviation_seconds > self._time_correction_threshold_seconds
        )
        errors = self._decode_errors(data)
        errors["time_correction"] = time_correction_recommended
        sensors: dict[str, Any] = {
            "ph": self._word(data, 14) / 100,
            "chlorine": self._word(data, 16) / 100,
            "air_temperature": self._air_temperature,
            "water_temperature": self._water_temperature,
            "water_level": data[27] + self._water_level_offset,
            "water_level_probe": data[27],
            "system_date": device_datetime.strftime("%d.%m.%Y"),
            "system_time": device_datetime.strftime("%H:%M:%S"),
            "time_deviation": self._duration(deviation_seconds),
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
            "error_status": self._error_status(
                errors, self._water_level_error_labels
            ),
            "warning_byte": warning_byte,
            "warning_byte_binary": f"{warning_byte:08b}",
            "error_byte": error_byte,
            "error_byte_binary": f"{error_byte:08b}",
            "relay_byte": relay_byte,
            "relay_byte_binary": f"{relay_byte:08b}",
            "byte24": byte24,
            "byte24_binary": f"{byte24:08b}",
            "raw_status": data[78],
        }
        return DecodedData(
            sensors,
            errors,
            relays,
            replace(self._status),
            {
                "minimum_payload_length": MIN_PAYLOAD_LENGTH,
                "payload_hex": frame[:MIN_PAYLOAD_LENGTH].hex(),
                "warning_byte": warning_byte,
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

    def _update_filtration_mode(self, data: bytes) -> None:
        mode = data[37]
        if mode in FILTRATION_NONSTOP_24H_VALUES:
            self._status.nonstop_24h = True
            self._status.timer = False
        elif mode in FILTRATION_TIMER_VALUES:
            self._status.nonstop_24h = False
            self._status.timer = True

    @staticmethod
    def _decode_errors(data: bytes) -> dict[str, bool]:
        return {
            key: bool(data[byte_index] & (1 << bit))
            for key, byte_index, bit, _ in ERROR_BITS
        }

    @staticmethod
    def _error_status(errors: dict[str, bool], water_level_labels: bool) -> str:
        labels = (
            WATER_LEVEL_ERROR_STATUS_MESSAGES
            if water_level_labels
            else ERROR_STATUS_MESSAGES
        )
        messages = [
            labels[key]
            for key in ERROR_STATUS_ORDER
            if errors.get(key)
        ]
        return "OK" if not messages else " | ".join(messages)

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
        try:
            return datetime(
                data[6] + 2000, data[7], data[8], data[9], data[10], data[11]
            )
        except ValueError as err:
            raise InvalidFrameError(f"invalid controller datetime: {err}") from err


def compact_hex(data: bytes | bytearray) -> str:
    """Return a bounded head/tail hex dump for debug logs and diagnostics."""
    raw = bytes(data)
    if len(raw) <= HEX_DUMP_BYTES:
        return raw.hex()
    half = HEX_DUMP_BYTES // 2
    return f"{raw[:half].hex()}...{raw[-half:].hex()}"
