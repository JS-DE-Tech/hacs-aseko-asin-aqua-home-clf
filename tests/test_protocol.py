from datetime import datetime
import importlib.util
from pathlib import Path
import sys

import pytest

spec = importlib.util.spec_from_file_location(
    "aseko_protocol", Path("custom_components/aseko_asin_aqua_home/protocol.py")
)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
AsekoProtocolDecoder = module.AsekoProtocolDecoder
FrameBuffer = module.FrameBuffer
BINARY_WIRE_FRAME_LENGTH = module.BINARY_WIRE_FRAME_LENGTH
FRAME_LENGTH = module.FRAME_LENGTH
InvalidFrameError = module.InvalidFrameError

PRODUCTION_SHIFTED_CAPTURE = bytes.fromhex(
    "02a4069132d702011a06120f191e000002c6001a001a00299a017200fb6eaa0c1d81"
    "00000000004b023f069132d702031a06120f191e4703001c090012001600171e02ba01"
    "02050c0006012802580384b271069132d702021a06120f191e0026003c003c003c0001"
    "6c6d6e6f012c2002580f0f0f"
)
# These bytes only complete the synthetic 120-byte fixture. The first two bytes
# fill currently mapped payload positions 114..115; the final four bytes are the
# undecoded binary wire-frame tail. No protocol meaning is assigned to them here.
SYNTHETIC_COMPLETION_BYTES = b"\x00\x00\xa5\xc3\x5a\x7e"


def frame(**values):
    data = bytearray(FRAME_LENGTH)
    now = datetime.now()
    data[0:4] = b"\x06\x91\x32\xd7"
    data[4:6] = bytes([2, 1])
    data[40:46] = b"\x06\x91\x32\xd7\x02\x03"
    data[80:86] = b"\x06\x91\x32\xd7\x02\x02"
    data[6:12] = bytes(
        [now.year - 2000, now.month, now.day, now.hour, now.minute, now.second]
    )
    data[14:18] = bytes([0, 0x2D, 0, 0x7B])
    data[23:27] = bytes([0, 200, 0, 250])
    for index, value in values.items():
        data[int(index)] = value
    return bytes(data)


def wire_frame(**values):
    payload = frame(**values)
    return payload + b"\xa5\xc3\x5a\x7e"


def test_fragmented_valid_payload():
    payload = wire_frame()
    buf = FrameBuffer()
    assert buf.feed(payload[:30]) == []
    updates = buf.feed(payload[30:])
    assert [update.sensors["ph"] for update in updates] == [0.45]
    assert buf.pending_bytes == 0


def test_multiple_payloads_in_one_read():
    updates = FrameBuffer().feed(wire_frame() + wire_frame(**{"13": 1}))
    assert len(updates) == 2
    assert not updates[0].errors["hour_dosing_exceeded"]
    assert updates[1].errors["hour_dosing_exceeded"]


def test_leading_garbage_bytes_are_discarded():
    buf = FrameBuffer()
    updates = buf.feed(b"garbage" + wire_frame())
    assert len(updates) == 1
    assert any("leading unsynchronized" in event.reason for event in buf.events)


def test_recovers_after_invalid_candidate():
    buf = FrameBuffer()
    invalid = bytearray(wire_frame(**{"57": 145}))
    updates = buf.feed(bytes(invalid) + wire_frame(**{"29": 8}))
    assert len(updates) == 1
    assert updates[0].relays["filtration"]
    assert any(not event.accepted for event in buf.events)


def test_mapped_payload_alone_is_not_a_complete_wire_frame():
    buf = FrameBuffer()
    assert buf.feed(frame()) == []
    assert buf.pending_bytes == FRAME_LENGTH
    assert any(event.status == "incomplete" for event in buf.events)


def test_shifted_production_capture_retains_partial_start_without_decoding():
    buf = FrameBuffer()
    assert len(PRODUCTION_SHIFTED_CAPTURE) == FRAME_LENGTH

    updates = buf.feed(PRODUCTION_SHIFTED_CAPTURE)

    assert updates == []
    assert buf.pending_bytes == FRAME_LENGTH - 2
    assert any(event.offset == 0 and event.status == "rejected" for event in buf.events)
    assert any(event.discarded_bytes == 2 for event in buf.events)
    assert any(event.status == "incomplete" for event in buf.events)


def test_shifted_production_capture_decodes_once_after_synthetic_completion():
    buf = FrameBuffer()
    assert buf.feed(PRODUCTION_SHIFTED_CAPTURE) == []

    updates = buf.feed(SYNTHETIC_COMPLETION_BYTES)

    assert len(updates) == 1
    assert buf.pending_bytes == 0
    decoded = updates[0]
    assert decoded.sensors["system_date"] == "18.06.2026"
    assert decoded.sensors["system_time"] == "15:25:30"
    assert decoded.sensors["ph"] == pytest.approx(7.10)
    assert decoded.sensors["chlorine"] == pytest.approx(0.26)
    assert decoded.sensors["pool_volume"] == 38
    assert decoded.sensors["dosing_delay"] == 5
    assert decoded.sensors["startup_delay"] == 10
    assert decoded.raw_fields["binary_wire_frame_length"] == BINARY_WIRE_FRAME_LENGTH
    assert decoded.raw_fields["undecoded_tail_hex"] == "a5c35a7e"
    assert sum(1 for event in buf.events if event.accepted) == 1


def test_incomplete_trailing_wire_frame_is_retained_after_complete_frame():
    first = wire_frame(**{"13": 1})
    trailing = wire_frame(**{"13": 2})[:70]
    buf = FrameBuffer()

    updates = buf.feed(first + trailing)

    assert len(updates) == 1
    assert updates[0].errors["hour_dosing_exceeded"]
    assert buf.pending_bytes == len(trailing)


def test_arbitrary_tcp_fragmentation_decodes_valid_frame_once():
    payload = wire_frame(**{"29": 8})
    buf = FrameBuffer()
    updates = []
    for size in (1, 2, 7, 13, 29, 31):
        updates.extend(buf.feed(payload[:size]))
        payload = payload[size:]
    updates.extend(buf.feed(payload))

    assert len(updates) == 1
    assert updates[0].relays["filtration"]
    assert buf.pending_bytes == 0


def test_invalid_structure_followed_by_valid_frame_resynchronizes():
    invalid = bytearray(wire_frame())
    invalid[45] = 4
    buf = FrameBuffer()

    updates = buf.feed(bytes(invalid) + wire_frame(**{"29": 8}))

    assert len(updates) == 1
    assert updates[0].relays["filtration"]
    assert any(event.status == "rejected" for event in buf.events)


def test_rejected_and_incomplete_input_do_not_mutate_decoder_state():
    decoder = AsekoProtocolDecoder()
    baseline = decoder.decode(frame(**{"23": 0, "24": 200, "25": 0, "26": 250, "78": 130}))
    assert baseline.status.heating
    buf = FrameBuffer(decoder=decoder)

    assert buf.feed(PRODUCTION_SHIFTED_CAPTURE) == []
    retained_after_partial = decoder.decode(
        frame(**{"23": 2, "24": 0, "25": 2, "26": 0, "78": 0})
    )
    assert retained_after_partial.status.heating
    assert retained_after_partial.sensors["air_temperature"] == 20
    assert retained_after_partial.sensors["water_temperature"] == 25

    rejecting_buf = FrameBuffer(decoder=decoder)
    invalid = bytearray(wire_frame(**{"7": 13, "23": 2, "24": 0, "25": 2, "26": 0, "78": 226}))
    assert rejecting_buf.feed(bytes(invalid)) == []

    retained = decoder.decode(frame(**{"23": 2, "24": 0, "25": 2, "26": 0, "78": 0}))
    assert retained.status.heating
    assert retained.sensors["air_temperature"] == 20
    assert retained.sensors["water_temperature"] == 25


def test_invalid_schedule_minute_rejected():
    with pytest.raises(InvalidFrameError, match="filter 1 start minute"):
        AsekoProtocolDecoder().decode(frame(**{"57": 145}))


@pytest.mark.parametrize(
    ("index", "value", "expected"),
    [
        (7, 13, "month"),
        (8, 0, "day"),
        (9, 24, "hour"),
        (10, 60, "minute"),
        (11, 60, "second"),
    ],
)
def test_invalid_date_and_time_values_rejected(index, value, expected):
    with pytest.raises(InvalidFrameError, match=expected):
        AsekoProtocolDecoder().decode(frame(**{str(index): value}))


def test_impossible_calendar_date_rejected():
    with pytest.raises(InvalidFrameError, match="invalid controller datetime"):
        AsekoProtocolDecoder().decode(frame(**{"7": 2, "8": 31}))


def test_invalid_ph_and_chlorine_rejected():
    with pytest.raises(InvalidFrameError, match="pH"):
        AsekoProtocolDecoder().decode(frame(**{"14": 6, "15": 0}))
    with pytest.raises(InvalidFrameError, match="chlorine"):
        AsekoProtocolDecoder().decode(frame(**{"16": 8, "17": 0}))


def test_negative_air_temperature():
    assert (
        AsekoProtocolDecoder()
        .decode(frame(**{"23": 255, "24": 156}))
        .sensors["air_temperature"]
        == -10
    )


def test_implausible_temperature_falls_back():
    decoder = AsekoProtocolDecoder()
    decoder.decode(frame())
    result = decoder.decode(frame(**{"23": 2, "24": 0, "25": 2, "26": 0}))
    assert result.sensors["air_temperature"] == 20
    assert result.sensors["water_temperature"] == 25


def test_error_and_relay_bits():
    result = AsekoProtocolDecoder().decode(
        frame(**{"13": 0b10000101, "29": 0b01001010})
    )
    assert (
        result.errors["hour_dosing_exceeded"]
        and result.errors["no_probe_flow"]
        and result.errors["chlorine_doses_without_change"]
    )
    assert (
        result.relays["filling"]
        and result.relays["filtration"]
        and result.relays["chlorine"]
    )


def test_stateful_status_handling():
    decoder = AsekoProtocolDecoder()
    assert decoder.decode(frame(**{"78": 130})).status.heating
    opened = decoder.decode(frame(**{"78": 40})).status
    assert opened.open_menu and opened.heating
    retained = decoder.decode(frame(**{"78": 0})).status
    assert retained.open_menu and retained.heating
    stopped = decoder.decode(frame(**{"78": 226})).status
    assert not stopped.filtration and not stopped.heating and not stopped.open_menu


def test_default_water_level_offset():
    result = AsekoProtocolDecoder().decode(frame(**{"27": 110}))
    assert result.sensors["water_level_probe"] == 110
    assert result.sensors["water_level"] == 143


def test_positive_custom_water_level_offset():
    result = AsekoProtocolDecoder(water_level_offset=20).decode(frame(**{"27": 110}))
    assert result.sensors["water_level_probe"] == 110
    assert result.sensors["water_level"] == 130


def test_negative_custom_water_level_offset():
    result = AsekoProtocolDecoder(water_level_offset=-20).decode(frame(**{"27": 110}))
    assert result.sensors["water_level_probe"] == 110
    assert result.sensors["water_level"] == 90


def test_frame_buffer_passes_water_level_offset():
    updates = FrameBuffer(water_level_offset=20).feed(wire_frame(**{"27": 110}))
    assert updates[0].sensors["water_level"] == 130


def test_short_frame_rejected():
    with pytest.raises(InvalidFrameError):
        AsekoProtocolDecoder().decode(b"short")


def test_minute_settings_decode_integral_seconds_without_fractional_minutes():
    result = AsekoProtocolDecoder().decode(
        frame(
            **{
                "76": 900 // 256,
                "77": 900 % 256,
                "106": 300 // 256,
                "107": 300 % 256,
            }
        )
    )
    assert result.sensors["filling_time_limit"] == 15
    assert result.sensors["dosing_delay"] == 5
