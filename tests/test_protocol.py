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
InvalidFrameError = module.InvalidFrameError
MIN_PAYLOAD_LENGTH = module.MIN_PAYLOAD_LENGTH

# Deliberately larger than the decoded payload. These capture-shaped fixtures prove
# synchronization does not infer the real TCP frame length from offset data[115].
WIRE_FRAME_LENGTH = 128


def wire_frame(**values) -> bytes:
    data = bytearray(
        [0] * MIN_PAYLOAD_LENGTH + [0xA5] * (WIRE_FRAME_LENGTH - MIN_PAYLOAD_LENGTH)
    )
    now = datetime.now()
    data[6:12] = bytes(
        [now.year - 2000, now.month, now.day, now.hour, now.minute, now.second]
    )
    data[14:18] = bytes([0, 0x2D, 0, 0x7B])  # pH 0.45, chlorine 1.23
    data[23:27] = bytes([0, 200, 0, 250])  # air 20.0 C, water 25.0 C
    data[56:64] = bytes([6, 30, 9, 15, 18, 0, 22, 45])
    data[69:71] = bytes([7, 10])
    for index, value in values.items():
        data[int(index)] = value
    return bytes(data)


def payload(**values) -> bytes:
    return wire_frame(**values)[:MIN_PAYLOAD_LENGTH]


def test_leading_garbage_is_discarded_before_valid_frame():
    parser = FrameBuffer()
    updates = parser.feed(b"garbage" + wire_frame() + wire_frame(**{"13": 1}))
    assert len(updates) == 1
    assert updates[0].sensors["chlorine"] == 1.23
    assert parser.detected_frame_length == WIRE_FRAME_LENGTH
    assert any("leading unsynchronized" in event.reason for event in parser.events)


def test_fragmented_frame_is_retained_until_next_boundary_is_verified():
    parser = FrameBuffer()
    first = wire_frame()
    second = wire_frame(**{"13": 1})
    assert parser.feed(first[:43]) == []
    assert parser.feed(first[43:] + second[:21]) == []
    updates = parser.feed(second[21:])
    assert len(updates) == 1
    assert updates[0].sensors["filter_1_start"] == "06:30"
    assert parser.pending_bytes == WIRE_FRAME_LENGTH


def test_multiple_valid_frames_in_one_tcp_read():
    parser = FrameBuffer()
    updates = parser.feed(
        wire_frame() + wire_frame(**{"13": 1}) + wire_frame(**{"29": 2})
    )
    assert len(updates) == 2
    assert not updates[0].errors["hour_dosing_exceeded"]
    assert updates[1].errors["hour_dosing_exceeded"]


def test_recovers_after_invalid_shifted_candidate():
    parser = FrameBuffer()
    invalid = wire_frame(**{"7": 0})
    updates = parser.feed(
        wire_frame() + invalid + wire_frame(**{"13": 1}) + wire_frame()
    )
    assert len(updates) == 2
    assert updates[1].errors["hour_dosing_exceeded"]
    assert any(not event.accepted for event in parser.events)


def test_invalid_candidate_does_not_publish_update():
    parser = FrameBuffer()
    invalid = wire_frame(**{"57": 145})
    assert parser.feed(invalid + wire_frame()) == []
    updates = parser.feed(wire_frame())
    assert len(updates) == 1
    assert updates[0].sensors["filter_1_start"] == "06:30"


def test_negative_air_temperature():
    assert (
        AsekoProtocolDecoder()
        .decode(payload(**{"23": 255, "24": 156}))
        .sensors["air_temperature"]
        == -10
    )


def test_implausible_temperature_falls_back():
    decoder = AsekoProtocolDecoder()
    decoder.decode(payload())
    result = decoder.decode(payload(**{"23": 2, "24": 0, "25": 2, "26": 0}))
    assert result.sensors["air_temperature"] == 20
    assert result.sensors["water_temperature"] == 25


def test_error_and_relay_bits():
    result = AsekoProtocolDecoder().decode(
        payload(**{"13": 0b10000101, "29": 0b01001010})
    )
    assert result.errors["hour_dosing_exceeded"]
    assert result.errors["no_probe_flow"]
    assert result.errors["chlorine_doses_without_change"]
    assert result.relays["filling"]
    assert result.relays["filtration"]
    assert result.relays["chlorine"]


def test_stateful_status_handling():
    decoder = AsekoProtocolDecoder()
    assert decoder.decode(payload(**{"78": 130})).status.heating
    opened = decoder.decode(payload(**{"78": 40})).status
    assert opened.open_menu and opened.heating
    retained = decoder.decode(payload(**{"78": 0})).status
    assert retained.open_menu and retained.heating
    stopped = decoder.decode(payload(**{"78": 226})).status
    assert not stopped.filtration and not stopped.heating and not stopped.open_menu


@pytest.mark.parametrize(
    ("index", "value", "reason"),
    [(7, 0, "month"), (9, 24, "hour"), (10, 60, "minute"), (11, 60, "second")],
)
def test_invalid_datetime_fields_are_rejected(index, value, reason):
    with pytest.raises(InvalidFrameError, match=reason):
        AsekoProtocolDecoder().decode(payload(**{str(index): value}))


def test_invalid_schedule_minute_is_rejected():
    with pytest.raises(InvalidFrameError, match="filter 1 start minute"):
        AsekoProtocolDecoder().decode(payload(**{"57": 145}))


def test_implausible_chlorine_is_rejected():
    with pytest.raises(InvalidFrameError, match="chlorine"):
        AsekoProtocolDecoder(max_chlorine=5).decode(payload(**{"16": 2, "17": 0}))


def test_short_frame_is_rejected():
    with pytest.raises(InvalidFrameError, match="too short"):
        AsekoProtocolDecoder().decode(b"short")
