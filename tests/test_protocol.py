from datetime import datetime
import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "aseko_protocol", Path("custom_components/aseko_asin_aqua_home/protocol.py")
)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
AsekoProtocolDecoder, FrameBuffer, FRAME_LENGTH = (
    module.AsekoProtocolDecoder,
    module.FrameBuffer,
    module.FRAME_LENGTH,
)


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


def test_fragmented_and_multiple_frames():
    a = frame()
    b = frame(**{"13": 1})
    buf = FrameBuffer()
    assert buf.feed(a[:30]) == []
    assert buf.feed(a[30:] + b) == [a, b]
    assert buf.pending_bytes == 0


def test_negative_air_temperature():
    assert (
        AsekoProtocolDecoder()
        .decode(frame(**{"23": 255, "24": 156}))
        .sensors["air_temperature"]
        == -10
    )


def test_implausible_temperature_falls_back():
    d = AsekoProtocolDecoder()
    d.decode(frame())
    result = d.decode(frame(**{"23": 2, "24": 0, "25": 2, "26": 0}))
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
    d = AsekoProtocolDecoder()
    assert d.decode(frame(**{"78": 130})).status.heating
    opened = d.decode(frame(**{"78": 40})).status
    assert opened.open_menu and opened.heating
    retained = d.decode(frame(**{"78": 0})).status
    assert retained.open_menu and retained.heating
    stopped = d.decode(frame(**{"78": 226})).status
    assert not stopped.filtration and not stopped.heating and not stopped.open_menu


def test_short_frame_rejected():
    import pytest

    with pytest.raises(ValueError):
        AsekoProtocolDecoder().decode(b"short")
