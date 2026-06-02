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
FRAME_LENGTH = module.FRAME_LENGTH
InvalidFrameError = module.InvalidFrameError


def frame(**values):
    data = bytearray(FRAME_LENGTH)
    now = datetime.now()
    data[6:12] = bytes(
        [now.year - 2000, now.month, now.day, now.hour, now.minute, now.second]
    )
    data[14:18] = bytes([0, 0x2D, 0, 0x7B])
    data[23:27] = bytes([0, 200, 0, 250])
    for index, value in values.items():
        data[int(index)] = value
    return bytes(data)


def test_fragmented_valid_payload():
    payload = frame()
    buf = FrameBuffer()
    assert buf.feed(payload[:30]) == []
    updates = buf.feed(payload[30:])
    assert [update.sensors["ph"] for update in updates] == [0.45]
    assert buf.pending_bytes == 0


def test_multiple_payloads_in_one_read():
    updates = FrameBuffer().feed(frame() + frame(**{"13": 1}))
    assert len(updates) == 2
    assert not updates[0].errors["hour_dosing_exceeded"]
    assert updates[1].errors["hour_dosing_exceeded"]


def test_leading_garbage_bytes_are_discarded():
    buf = FrameBuffer()
    updates = buf.feed(b"garbage" + frame())
    assert len(updates) == 1
    assert any("leading unsynchronized" in event.reason for event in buf.events)


def test_recovers_after_invalid_candidate():
    buf = FrameBuffer()
    updates = buf.feed(frame(**{"57": 145}) + frame(**{"29": 8}))
    assert len(updates) == 1
    assert updates[0].relays["filtration"]
    assert any(not event.accepted for event in buf.events)


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
    updates = FrameBuffer(water_level_offset=20).feed(frame(**{"27": 110}))
    assert updates[0].sensors["water_level"] == 130


def test_short_frame_rejected():
    with pytest.raises(InvalidFrameError):
        AsekoProtocolDecoder().decode(b"short")
