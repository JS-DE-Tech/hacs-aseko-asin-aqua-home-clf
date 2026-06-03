from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import sys
import types

import asyncio

import pytest

BASE = Path("custom_components/aseko_asin_aqua_home")
PACKAGE = "aseko_backwash_test"


class FakeStore:
    saved_by_key = {}

    def __init__(self, hass, major_version, key):
        self.key = key

    async def async_load(self):
        return self.saved_by_key.get(self.key)

    async def async_save(self, data):
        self.saved_by_key[self.key] = data


@pytest.fixture
def backwash_module(monkeypatch):
    FakeStore.saved_by_key = {}
    homeassistant = types.ModuleType("homeassistant")
    core = types.ModuleType("homeassistant.core")
    helpers = types.ModuleType("homeassistant.helpers")
    storage = types.ModuleType("homeassistant.helpers.storage")
    core.HomeAssistant = object
    storage.Store = FakeStore
    for name, module in {
        "homeassistant": homeassistant,
        "homeassistant.core": core,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.storage": storage,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    package = types.ModuleType(PACKAGE)
    package.__path__ = [str(BASE)]
    monkeypatch.setitem(sys.modules, PACKAGE, package)
    spec = importlib.util.spec_from_file_location(
        f"{PACKAGE}.backwash_tracker", BASE / "backwash_tracker.py"
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def _tracker(backwash_module):
    return backwash_module.BackwashTracker(types.SimpleNamespace(), "entry-1")


def _observe_completed_cycle(tracker, start, duration_seconds):
    assert tracker.observe_relay(True, start) is False
    if duration_seconds > 60:
        assert tracker.observe_relay(True, start + timedelta(seconds=60)) is False
    elif duration_seconds > 1:
        assert (
            tracker.observe_relay(True, start + timedelta(seconds=duration_seconds / 2))
            is False
        )
    return tracker.observe_relay(False, start + timedelta(seconds=duration_seconds))


def test_inactive_relay_produces_no_timestamp(backwash_module):
    tracker = _tracker(backwash_module)
    start = datetime(2026, 1, 1, 6, 20, tzinfo=timezone.utc)

    assert tracker.observe_relay(False, start) is False
    assert tracker.observe_relay(False, start + timedelta(seconds=120)) is False
    assert tracker.last_backwash is None


def test_unknown_previous_state_active_61_seconds_then_inactive_records(
    backwash_module,
):
    tracker = _tracker(backwash_module)
    start = datetime(2026, 1, 1, 6, 20, tzinfo=timezone.utc)

    assert _observe_completed_cycle(tracker, start, 61) is True
    assert tracker.last_backwash == start
    assert tracker.state.last_backwash_timestamp == start.isoformat()
    assert tracker.state.active_since_timestamp is None


def test_inactive_previous_state_active_61_seconds_then_inactive_records(
    backwash_module,
):
    tracker = _tracker(backwash_module)
    start = datetime(2026, 1, 1, 6, 20, tzinfo=timezone.utc)

    assert tracker.observe_relay(False, start - timedelta(seconds=1)) is False
    assert _observe_completed_cycle(tracker, start, 61) is True
    assert tracker.last_backwash == start


@pytest.mark.parametrize("duration_seconds", [59, 60])
def test_completed_cycle_at_or_below_threshold_is_not_recorded(
    backwash_module, duration_seconds
):
    tracker = _tracker(backwash_module)
    start = datetime(2026, 1, 1, 6, 20, tzinfo=timezone.utc)

    assert _observe_completed_cycle(tracker, start, duration_seconds) is False
    assert tracker.last_backwash is None


@pytest.mark.parametrize("duration_seconds", [61, 69])
def test_completed_cycle_above_threshold_is_recorded(backwash_module, duration_seconds):
    tracker = _tracker(backwash_module)
    start = datetime(2026, 1, 1, 6, 20, tzinfo=timezone.utc)

    assert _observe_completed_cycle(tracker, start, duration_seconds) is True
    assert tracker.last_backwash == start


def test_active_longer_than_threshold_without_inactive_transition_does_not_record(
    backwash_module,
):
    tracker = _tracker(backwash_module)
    start = datetime(2026, 1, 1, 6, 20, tzinfo=timezone.utc)

    assert tracker.observe_relay(True, start) is False
    assert tracker.observe_relay(True, start + timedelta(seconds=60)) is False
    assert tracker.observe_relay(True, start + timedelta(seconds=120)) is False
    assert tracker.last_backwash is None
    assert tracker.state.active_since_timestamp == start.isoformat()


def test_completed_cycle_records_exactly_once(backwash_module):
    tracker = _tracker(backwash_module)
    start = datetime(2026, 1, 1, 6, 20, tzinfo=timezone.utc)

    assert tracker.observe_relay(True, start) is False
    assert tracker.observe_relay(True, start + timedelta(seconds=60)) is False
    assert tracker.observe_relay(False, start + timedelta(seconds=61)) is True
    assert tracker.last_backwash == start
    assert tracker.observe_relay(False, start + timedelta(seconds=62)) is False
    assert tracker.observe_relay(False, start + timedelta(seconds=63)) is False
    assert tracker.last_backwash == start


def test_later_independent_completed_cycle_updates_last_backwash(backwash_module):
    tracker = _tracker(backwash_module)
    first = datetime(2026, 1, 1, 6, 20, tzinfo=timezone.utc)
    second = first + timedelta(hours=2)

    assert _observe_completed_cycle(tracker, first, 61) is True
    assert tracker.last_backwash == first
    assert tracker.observe_relay(False, second - timedelta(seconds=1)) is False
    assert _observe_completed_cycle(tracker, second, 69) is True
    assert tracker.last_backwash == second


def test_long_observation_gap_does_not_create_false_event(backwash_module):
    tracker = _tracker(backwash_module)
    start = datetime(2026, 1, 1, 6, 20, tzinfo=timezone.utc)

    assert tracker.observe_relay(True, start) is False
    assert tracker.observe_relay(False, start + timedelta(seconds=61)) is False
    assert tracker.last_backwash is None
    assert tracker.state.active_since_timestamp is None


def test_backwash_storage_survives_reload(backwash_module):
    tracker = _tracker(backwash_module)
    start = datetime(2026, 1, 1, 6, 20, tzinfo=timezone.utc)
    assert tracker.store_key == "aseko_asin_aqua_home_backwash_tracker"
    assert backwash_module.STORAGE_VERSION == 1
    assert _observe_completed_cycle(tracker, start, 61) is True
    asyncio.run(tracker.async_save())

    reloaded = _tracker(backwash_module)
    asyncio.run(reloaded.async_load())
    assert reloaded.last_backwash == start
    assert reloaded.last_backwash.tzinfo is not None
    assert reloaded.state.last_backwash_timestamp == start.isoformat()


def test_legacy_entry_id_backwash_storage_migrates_to_stable_key(backwash_module):
    legacy_key = "aseko_asin_aqua_home_backwash_tracker_entry-1"
    stable_key = "aseko_asin_aqua_home_backwash_tracker"
    timestamp = "2026-01-01T06:20:00+00:00"
    FakeStore.saved_by_key[legacy_key] = {
        "version": 1,
        "state": {"last_backwash_timestamp": timestamp},
    }

    tracker = _tracker(backwash_module)
    asyncio.run(tracker.async_load())

    assert tracker.store_key == stable_key
    assert tracker.state.last_backwash_timestamp == timestamp
    assert (
        FakeStore.saved_by_key[stable_key]["state"]["last_backwash_timestamp"]
        == timestamp
    )
