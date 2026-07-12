from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import sys
import types

import pytest

import asyncio


def load_tracker(monkeypatch, store_payload=None):
    homeassistant = types.ModuleType("homeassistant")
    core = types.ModuleType("homeassistant.core")
    helpers = types.ModuleType("homeassistant.helpers")
    storage = types.ModuleType("homeassistant.helpers.storage")
    util = types.ModuleType("homeassistant.util")
    dt = types.ModuleType("homeassistant.util.dt")

    saved = []

    class Store:
        def __init__(self, hass, major_version, key):
            self.key = key
            self.major_version = major_version

        async def async_load(self):
            if isinstance(store_payload, dict) and any(
                key.startswith("aseko_asin_aqua_home_dosing_tracker")
                for key in store_payload
            ):
                return store_payload.get(self.key)
            return store_payload

        async def async_save(self, data):
            saved.append((self.key, data))

    core.HomeAssistant = object
    storage.Store = Store
    dt.as_local = lambda value: value.astimezone(timezone(timedelta(hours=1)))
    monkeypatch.setitem(sys.modules, "homeassistant", homeassistant)
    monkeypatch.setitem(sys.modules, "homeassistant.core", core)
    monkeypatch.setitem(sys.modules, "homeassistant.helpers", helpers)
    monkeypatch.setitem(sys.modules, "homeassistant.helpers.storage", storage)
    monkeypatch.setitem(sys.modules, "homeassistant.util", util)
    monkeypatch.setitem(sys.modules, "homeassistant.util.dt", dt)

    spec = importlib.util.spec_from_file_location(
        "aseko_dosing_tracker_test",
        Path("custom_components/aseko_asin_aqua_home/dosing_tracker.py"),
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module, saved


def test_runtime_accumulates_only_while_relay_active(monkeypatch):
    module, _ = load_tracker(monkeypatch)
    tracker = module.DosingTracker(types.SimpleNamespace(), "entry-1")
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    tracker.observe_relays({"chlorine": True}, start)
    tracker.observe_relays({"chlorine": True}, start + timedelta(seconds=10))
    tracker.observe_relays({"chlorine": False}, start + timedelta(seconds=20))
    tracker.observe_relays({"chlorine": False}, start + timedelta(seconds=30))
    assert tracker.states["chlorine"].accumulated_runtime_seconds == 20


def test_all_channels_and_simultaneous_relays_are_independent(monkeypatch):
    module, _ = load_tracker(monkeypatch)
    tracker = module.DosingTracker(types.SimpleNamespace(), "entry-1")
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    tracker.observe_relays({"chlorine": True, "ph_minus": True}, start)
    tracker.observe_relays(
        {"chlorine": True, "ph_minus": True, "flocculation": True},
        start + timedelta(seconds=15),
    )
    tracker.observe_relays(
        {"chlorine": False, "ph_minus": True, "flocculation": True},
        start + timedelta(seconds=30),
    )
    assert tracker.states["chlorine"].accumulated_runtime_seconds == 30
    assert tracker.states["ph_minus"].accumulated_runtime_seconds == 30
    assert tracker.states["flocculation"].accumulated_runtime_seconds == 15
    assert tracker.states["algicide"].accumulated_runtime_seconds == 0


def test_large_gaps_are_not_counted(monkeypatch):
    module, _ = load_tracker(monkeypatch)
    tracker = module.DosingTracker(types.SimpleNamespace(), "entry-1")
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    tracker.observe_relays({"chlorine": True}, start)
    tracker.observe_relays({"chlorine": True}, start + timedelta(seconds=61))
    assert tracker.states["chlorine"].accumulated_runtime_seconds == 0
    assert module.MAX_COUNTABLE_INTERVAL_SECONDS == 60


def test_storage_reload_schema_and_clean_save(monkeypatch):
    payload = {
        "version": 2,
        "channels": {
            "chlorine": {
                "accumulated_runtime_seconds": 123,
                "last_relay_state": True,
                "last_observed_timestamp": "2026-01-01T00:00:00+00:00",
                "last_container_replacement_timestamp": "2026-01-01T00:00:00+00:00",
                "last_calculated_flow_rate": 2.5,
                "daily_runtime_seconds": 45,
                "daily_runtime_date": "2026-01-01",
            }
        },
    }
    module, saved = load_tracker(monkeypatch, payload)
    tracker = module.DosingTracker(types.SimpleNamespace(), "entry-1")
    asyncio.run(tracker.async_load())
    assert tracker.store_key == "aseko_asin_aqua_home_dosing_tracker"
    assert tracker.states["chlorine"].accumulated_runtime_seconds == 123
    assert tracker.states["chlorine"].last_calculated_flow_rate == 2.5
    assert tracker.states["chlorine"].daily_runtime_seconds == 45
    assert tracker.states["chlorine"].daily_runtime_date == "2026-01-01"
    assert tracker.as_dict()["version"] == module.STORAGE_VERSION
    asyncio.run(tracker.async_save())
    assert saved[-1][1]["version"] == 2
    assert saved[-1][1]["channels"]["chlorine"]["last_calculated_flow_rate"] == 2.5


def test_container_reset_affects_only_selected_channel_and_persists(monkeypatch):
    module, saved = load_tracker(monkeypatch)
    tracker = module.DosingTracker(types.SimpleNamespace(), "entry-1")
    tracker.states["chlorine"].accumulated_runtime_seconds = 100
    tracker.states["ph_minus"].accumulated_runtime_seconds = 200
    asyncio.run(tracker.async_reset_container("chlorine"))
    assert tracker.states["chlorine"].accumulated_runtime_seconds == 0
    assert tracker.states["ph_minus"].accumulated_runtime_seconds == 200
    assert saved
    assert saved[-1][1]["channels"]["chlorine"]["last_container_replacement_timestamp"]


def test_channel_defaults(monkeypatch):
    module, _ = load_tracker(monkeypatch)
    defaults = {
        channel.key: channel.container_size_default
        for channel in module.DOSING_CHANNELS
    }
    assert defaults == {
        "chlorine": 20.0,
        "ph_minus": 20.0,
        "flocculation": 6.0,
        "algicide": 6.0,
    }


def test_legacy_entry_id_dosing_storage_migrates_to_stable_key(monkeypatch):
    legacy_payload = {
        "version": 2,
        "channels": {
            "chlorine": {"accumulated_runtime_seconds": 456},
        },
    }
    module, saved = load_tracker(
        monkeypatch,
        {"aseko_asin_aqua_home_dosing_tracker_entry-1": legacy_payload},
    )
    tracker = module.DosingTracker(types.SimpleNamespace(), "entry-1")

    asyncio.run(tracker.async_load())

    assert tracker.store_key == "aseko_asin_aqua_home_dosing_tracker"
    assert tracker.states["chlorine"].accumulated_runtime_seconds == 456
    assert saved[-1][0] == "aseko_asin_aqua_home_dosing_tracker"
    assert saved[-1][1]["channels"]["chlorine"]["accumulated_runtime_seconds"] == 456


def test_legacy_liters_per_hour_flow_rate_migrates_to_ml_per_min(monkeypatch):
    payload = {
        "version": 1,
        "channels": {
            "chlorine": {
                "accumulated_runtime_seconds": 607,
                "last_container_replacement_timestamp": "2026-01-01T00:00:00+00:00",
                "last_calculated_flow_rate": 1.2,
            }
        },
    }
    module, saved = load_tracker(monkeypatch, payload)
    tracker = module.DosingTracker(types.SimpleNamespace(), "entry-1")

    asyncio.run(tracker.async_load())

    state = tracker.states["chlorine"]
    assert state.last_calculated_flow_rate == pytest.approx(20.0)
    assert state.accumulated_runtime_seconds == 607
    assert state.last_container_replacement_timestamp == "2026-01-01T00:00:00+00:00"
    assert saved[-1][1]["version"] == 2
    assert saved[-1][1]["channels"]["chlorine"]["last_calculated_flow_rate"] == pytest.approx(20.0)


@pytest.mark.parametrize("channel_key", ["chlorine", "ph_minus", "flocculation", "algicide"])
def test_container_reset_persists_full_baseline_for_each_channel(monkeypatch, channel_key):
    module, saved = load_tracker(monkeypatch)
    tracker = module.DosingTracker(types.SimpleNamespace(), "entry-1")
    tracker.states[channel_key].accumulated_runtime_seconds = 123

    asyncio.run(tracker.async_reset_container(channel_key))

    timestamp = tracker.states[channel_key].last_container_replacement_timestamp
    assert tracker.states[channel_key].accumulated_runtime_seconds == 0
    assert timestamp is not None
    assert saved[-1][1]["channels"][channel_key]["accumulated_runtime_seconds"] == 0.0
    assert saved[-1][1]["channels"][channel_key]["last_container_replacement_timestamp"] == timestamp
    assert saved[-1][1]["channels"][channel_key]["last_observed_timestamp"] == timestamp

    module, _ = load_tracker(monkeypatch, saved[-1][1])
    reloaded = module.DosingTracker(types.SimpleNamespace(), "entry-1")
    asyncio.run(reloaded.async_load())
    assert reloaded.states[channel_key].accumulated_runtime_seconds == 0
    assert reloaded.states[channel_key].last_container_replacement_timestamp == timestamp
    assert reloaded.states[channel_key].last_observed_timestamp == timestamp


def test_container_reset_discards_pre_reset_active_interval(monkeypatch):
    module, _ = load_tracker(monkeypatch)
    tracker = module.DosingTracker(types.SimpleNamespace(), "entry-1")
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    tracker.observe_relays({"chlorine": True}, start)

    asyncio.run(tracker.async_reset_container("chlorine"))
    reset_timestamp = datetime.fromisoformat(
        tracker.states["chlorine"].last_container_replacement_timestamp
    )
    tracker.observe_relays({"chlorine": True}, reset_timestamp + timedelta(seconds=10))

    assert tracker.states["chlorine"].accumulated_runtime_seconds == 10


def test_daily_runtime_accumulates_within_local_day(monkeypatch):
    module, _ = load_tracker(monkeypatch)
    tracker = module.DosingTracker(types.SimpleNamespace(), "entry-1")
    start = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)

    tracker.observe_relays({"chlorine": True}, start)
    tracker.observe_relays({"chlorine": True}, start + timedelta(seconds=30))
    tracker.observe_relays({"chlorine": False}, start + timedelta(seconds=45))

    assert tracker.states["chlorine"].accumulated_runtime_seconds == 45
    assert tracker.states["chlorine"].daily_runtime_seconds == 45
    assert tracker.states["chlorine"].daily_runtime_date == "2026-01-01"


def test_daily_runtime_resets_at_local_midnight_without_resetting_total(monkeypatch):
    module, _ = load_tracker(monkeypatch)
    tracker = module.DosingTracker(types.SimpleNamespace(), "entry-1")
    before_midnight = datetime(2026, 1, 1, 22, 59, 50, tzinfo=timezone.utc)
    after_midnight = datetime(2026, 1, 1, 23, 0, 10, tzinfo=timezone.utc)

    tracker.observe_relays({"chlorine": True}, before_midnight)
    tracker.observe_relays({"chlorine": True}, after_midnight)

    assert tracker.states["chlorine"].accumulated_runtime_seconds == 20
    assert tracker.states["chlorine"].daily_runtime_seconds == 10
    assert tracker.states["chlorine"].daily_runtime_date == "2026-01-02"


def test_daily_runtime_survives_reload_without_double_counting(monkeypatch):
    payload = {
        "version": 2,
        "channels": {
            "chlorine": {
                "accumulated_runtime_seconds": 100,
                "daily_runtime_seconds": 40,
                "daily_runtime_date": "2026-01-01",
                "last_relay_state": True,
                "last_observed_timestamp": "2026-01-01T10:00:00+00:00",
            }
        },
    }
    module, _ = load_tracker(monkeypatch, payload)
    tracker = module.DosingTracker(types.SimpleNamespace(), "entry-1")
    asyncio.run(tracker.async_load())

    tracker.observe_relays(
        {"chlorine": True}, datetime(2026, 1, 1, 10, 0, 30, tzinfo=timezone.utc)
    )

    assert tracker.states["chlorine"].accumulated_runtime_seconds == 130
    assert tracker.states["chlorine"].daily_runtime_seconds == 70


def test_calculated_flow_rate_is_persisted_without_resetting_runtime(monkeypatch):
    module, saved = load_tracker(monkeypatch)
    tracker = module.DosingTracker(types.SimpleNamespace(), "entry-1")
    tracker.states["chlorine"].accumulated_runtime_seconds = 10 * 3600

    asyncio.run(tracker.async_store_calculated_flow_rate("chlorine", 2.0))

    assert tracker.states["chlorine"].accumulated_runtime_seconds == 10 * 3600
    assert tracker.states["chlorine"].last_calculated_flow_rate == 2.0
    assert saved[-1][1]["channels"]["chlorine"]["accumulated_runtime_seconds"] == 10 * 3600
    assert saved[-1][1]["channels"]["chlorine"]["last_calculated_flow_rate"] == 2.0
