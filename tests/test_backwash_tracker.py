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


def test_backwash_confirmation_state_machine_and_persistence(backwash_module):
    tracker = backwash_module.BackwashTracker(types.SimpleNamespace(), "entry-1")
    start = datetime(2026, 1, 1, 6, 20, tzinfo=timezone.utc)

    assert tracker.last_backwash is None
    assert tracker.observe_relay(False, start) is False
    assert tracker.observe_relay(True, start) is False
    assert tracker.observe_relay(True, start + timedelta(seconds=59)) is False
    assert tracker.last_backwash is None

    assert tracker.observe_relay(True, start + timedelta(seconds=60)) is True
    assert tracker.last_backwash == start
    assert tracker.observe_relay(True, start + timedelta(seconds=90)) is False
    assert tracker.last_backwash == start
    assert tracker.observe_relay(False, start + timedelta(seconds=100)) is False
    assert tracker.last_backwash == start

    second = start + timedelta(hours=2)
    assert tracker.observe_relay(True, second) is False
    assert tracker.observe_relay(False, second + timedelta(seconds=10)) is False
    assert tracker.last_backwash == start

    third = start + timedelta(hours=3)
    assert tracker.observe_relay(True, third) is False
    assert tracker.observe_relay(True, third + timedelta(seconds=60)) is True
    assert tracker.last_backwash == third


def test_long_observation_gap_restarts_active_candidate(backwash_module):
    tracker = backwash_module.BackwashTracker(types.SimpleNamespace(), "entry-1")
    start = datetime(2026, 1, 1, 6, 20, tzinfo=timezone.utc)

    assert tracker.observe_relay(True, start) is False
    assert tracker.observe_relay(True, start + timedelta(seconds=61)) is False
    assert tracker.last_backwash is None
    assert tracker.state.active_since_timestamp == (start + timedelta(seconds=61)).isoformat()
    assert tracker.observe_relay(True, start + timedelta(seconds=121)) is True
    assert tracker.last_backwash == start + timedelta(seconds=61)


def test_backwash_storage_survives_reload(backwash_module):
    tracker = backwash_module.BackwashTracker(types.SimpleNamespace(), "entry-1")
    start = datetime(2026, 1, 1, 6, 20, tzinfo=timezone.utc)
    assert tracker.store_key == "aseko_asin_aqua_home_backwash_tracker_entry-1"
    assert backwash_module.STORAGE_VERSION == 1
    tracker.observe_relay(True, start)
    assert tracker.observe_relay(True, start + timedelta(seconds=60)) is True
    asyncio.run(tracker.async_save())

    reloaded = backwash_module.BackwashTracker(types.SimpleNamespace(), "entry-1")
    asyncio.run(reloaded.async_load())
    assert reloaded.last_backwash == start
    assert reloaded.last_backwash.tzinfo is not None
    assert reloaded.state.event_recorded_for_current_cycle is True
