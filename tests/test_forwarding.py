"""Regression checks for Node-RED-compatible forwarding direction."""

from pathlib import Path


def test_cloud_forwarding_is_one_way_by_default():
    constants = Path("custom_components/aseko_asin_aqua_home/const.py").read_text()
    coordinator = Path(
        "custom_components/aseko_asin_aqua_home/coordinator.py"
    ).read_text()
    assert "DEFAULT_FORWARD_ENABLED = True" in constants
    assert "cloud_writer.write(chunk)" in coordinator
    assert "\n                writer.write(chunk)" not in coordinator
    assert "_relay_cloud" not in coordinator
    assert "_discard_cloud_responses" in coordinator
