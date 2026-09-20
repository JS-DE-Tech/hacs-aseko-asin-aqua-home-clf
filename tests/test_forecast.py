"""Behavioral forecast tests using the existing lightweight HA test harness."""

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

from test_entities import integration_modules

UTC = timezone.utc


@pytest.fixture
def forecast_module(integration_modules):
    return importlib.import_module("aseko_entity_test.forecast")


def seed(module, tracker, *, start="2026-09-01", count=3, runtime=600,
         observed=86400, active=86400, channel="chlorine"):
    day = datetime.fromisoformat(start).date()
    tracker.started_on = day.isoformat()
    for index in range(count):
        key = (day + timedelta(days=index)).isoformat()
        tracker.days[channel][key] = module.Day(key, 86400, observed, active, runtime)


def calculate(tracker, channel="chlorine", **kwargs):
    args = dict(remaining_liters=8.4, flow_rate_ml_min=60,
                sensors={"algicide_dose": 10, "flocculation_dose": 10},
                data_available=True, now=datetime(2026, 9, 4, 12, tzinfo=UTC))
    args.update(kwargs)
    return tracker.calculate(channel, **args)


def test_three_observed_days_produce_remaining_days(forecast_module):
    tracker = forecast_module.ConsumptionForecast(None)
    seed(forecast_module, tracker)
    result = calculate(tracker)
    assert result.status == "active"
    assert result.remaining_days == 14
    assert result.daily_consumption_ml == 600
    assert result.sample_days == 3


def test_recent_seven_active_days_receive_double_weight(forecast_module):
    tracker = forecast_module.ConsumptionForecast(None)
    seed(forecast_module, tracker, count=14, runtime=60)
    for day in list(tracker.days["chlorine"].values())[7:]:
        day.runtime_seconds = 120
    result = calculate(tracker, now=datetime(2026, 9, 15, tzinfo=UTC))
    assert result.daily_consumption_ml == 100
    assert result.sample_days == 14


@pytest.mark.parametrize("channel", ["chlorine", "ph_minus", "flocculation", "algicide"])
def test_each_channel_uses_its_own_runtime(forecast_module, channel):
    tracker = forecast_module.ConsumptionForecast(None)
    seed(forecast_module, tracker, channel=channel, runtime=60)
    assert calculate(tracker, channel).daily_consumption_ml == 60


@pytest.mark.parametrize("channel,key", [("algicide", "algicide_dose"), ("flocculation", "flocculation_dose")])
def test_zero_dose_pauses_without_deleting_history(forecast_module, channel, key):
    tracker = forecast_module.ConsumptionForecast(None)
    seed(forecast_module, tracker, channel=channel)
    original = deepcopy(tracker.days)
    assert calculate(tracker, channel, sensors={key: 0}).status == "paused"
    assert calculate(tracker, channel, sensors={key: 0}).remaining_days is None
    assert tracker.days == original
    assert calculate(tracker, channel, sensors={key: 1}).remaining_days == 14


def test_old_history_resumes_provisionally_after_weeks(forecast_module):
    tracker = forecast_module.ConsumptionForecast(None)
    seed(forecast_module, tracker, channel="algicide")
    for index in range(4, 25):
        key = f"2026-09-{index:02}"
        tracker.days["algicide"][key] = forecast_module.Day(key, 86400, 86400, 0, 0)
    result = calculate(tracker, "algicide", now=datetime(2026, 9, 25, tzinfo=UTC))
    assert result.status == "provisional"
    assert result.remaining_days == 14
    seed(forecast_module, tracker, channel="algicide", start="2026-09-25")
    assert calculate(tracker, "algicide", now=datetime(2026, 9, 28, tzinfo=UTC)).status == "active"


def test_current_day_excluded_and_low_coverage_not_treated_as_zero(forecast_module):
    tracker = forecast_module.ConsumptionForecast(None)
    seed(forecast_module, tracker, count=4)
    tracker.days["chlorine"]["2026-09-04"].runtime_seconds = 86400
    assert calculate(tracker).daily_consumption_ml == 600
    tracker.days["chlorine"]["2026-09-03"].observed_seconds = 3600
    result = calculate(tracker)
    assert result.status == "insufficient_data"
    assert result.sample_days == 2
    assert result.remaining_days is None


def test_no_consumption_learning_calibration_and_offline_states(forecast_module):
    tracker = forecast_module.ConsumptionForecast(None)
    assert calculate(tracker).status == "learning"
    assert calculate(tracker, flow_rate_ml_min=0).status == "calibration_missing"
    assert calculate(tracker, data_available=False).status == "device_data_missing"
    assert calculate(tracker, "algicide", sensors={}).status == "device_data_missing"
    seed(forecast_module, tracker, runtime=0)
    result = calculate(tracker)
    assert result.status == "no_consumption"
    assert result.remaining_days is None


def test_actual_zero_usage_days_are_included(forecast_module):
    tracker = forecast_module.ConsumptionForecast(None)
    seed(forecast_module, tracker, runtime=0)
    tracker.days["chlorine"]["2026-09-01"].runtime_seconds = 1800
    assert calculate(tracker).daily_consumption_ml == 600


def test_changed_flow_rate_recalculates_without_mutating_runtime(forecast_module):
    tracker = forecast_module.ConsumptionForecast(None)
    seed(forecast_module, tracker)
    before = deepcopy(tracker.days)
    assert calculate(tracker, flow_rate_ml_min=120).remaining_days == 7
    assert tracker.days == before
    assert calculate(tracker, remaining_liters=0).remaining_days == 0
    assert calculate(tracker, remaining_liters=0.5).remaining_days == 0


def test_observation_excludes_gaps_pause_and_clock_reversal(forecast_module, monkeypatch):
    monkeypatch.setattr(forecast_module.dt_util, "as_local", lambda value: value.astimezone(UTC))
    tracker = forecast_module.ConsumptionForecast(None)
    start = datetime(2026, 9, 1, tzinfo=UTC)
    for seconds, dose in ((0, 10), (60, 0), (120, 0), (180, 10), (240, 10), (400, 10)):
        tracker.observe({"algicide": True}, {"algicide_dose": dose}, start + timedelta(seconds=seconds))
    day = tracker.days["algicide"]["2026-09-01"]
    assert day.observed_seconds == 240
    assert day.active_seconds == 120
    assert day.runtime_seconds == 120
    tracker.observe({"algicide": True}, {"algicide_dose": 10}, start + timedelta(seconds=350))
    tracker.observe({"algicide": True}, {"algicide_dose": 10}, start + timedelta(seconds=460))
    assert day.runtime_seconds == 180


def test_mixed_pause_day_is_normalized_to_enabled_time(forecast_module):
    tracker = forecast_module.ConsumptionForecast(None)
    seed(forecast_module, tracker, active=43200, runtime=300)
    assert calculate(tracker).daily_consumption_ml == 600


def test_midnight_splits_real_intervals(forecast_module, monkeypatch):
    berlin = ZoneInfo("Europe/Berlin")
    monkeypatch.setattr(forecast_module.dt_util, "as_local", lambda value: value.astimezone(berlin))
    tracker = forecast_module.ConsumptionForecast(None)
    start = datetime(2026, 9, 1, 21, 59, 40, tzinfo=UTC)
    tracker.observe({"chlorine": True}, {}, start)
    tracker.advance_day(start + timedelta(seconds=20))
    tracker.observe({"chlorine": True}, {}, start + timedelta(seconds=60))
    assert tracker.days["chlorine"]["2026-09-01"].runtime_seconds == 20
    assert tracker.days["chlorine"]["2026-09-02"].runtime_seconds == 40


@pytest.mark.parametrize("day,hours", [("2026-03-29", 23), ("2026-10-25", 25)])
def test_day_length_and_observations_across_dst(forecast_module, monkeypatch, day, hours):
    berlin = ZoneInfo("Europe/Berlin")
    monkeypatch.setattr(forecast_module.dt_util, "as_local", lambda value: value.astimezone(berlin))
    tracker = forecast_module.ConsumptionForecast(None)
    start = datetime.fromisoformat(day).replace(tzinfo=berlin).astimezone(UTC)
    for second in range(0, hours * 3600 + 1, 60):
        tracker.observe({"chlorine": True}, {}, start + timedelta(seconds=second))
    record = tracker.days["chlorine"][day]
    assert record.day_seconds == hours * 3600
    assert record.observed_seconds == hours * 3600
    assert record.runtime_seconds == hours * 3600


def test_save_reload_and_disconnect_preserve_history_without_counting_downtime(forecast_module):
    tracker = forecast_module.ConsumptionForecast(None)
    start = datetime(2026, 9, 1, 12, tzinfo=UTC)
    tracker.observe({"chlorine": True}, {}, start)
    tracker.observe({"chlorine": True}, {}, start + timedelta(seconds=60))
    asyncio.run(tracker.async_save(force=True))
    snapshot = deepcopy(tracker._store.saved)
    reloaded = forecast_module.ConsumptionForecast(None)
    reloaded._store.async_load = AsyncMock(return_value=snapshot)
    asyncio.run(reloaded.async_load())
    reloaded.observe({"chlorine": True}, {}, start + timedelta(seconds=90))
    assert reloaded.days == tracker.days
    reloaded.break_observation()
    reloaded.observe({"chlorine": True}, {}, start + timedelta(seconds=120))
    assert reloaded.days == tracker.days


def test_future_storage_is_never_overwritten(forecast_module):
    tracker = forecast_module.ConsumptionForecast(None)
    tracker._store.async_load = AsyncMock(return_value={"version": 99, "channels": {"valuable": 1}})
    tracker._store.async_save = AsyncMock()
    with pytest.raises(ValueError, match="preserving"):
        asyncio.run(tracker.async_load())
    tracker._dirty = True
    asyncio.run(tracker.async_save(force=True))
    tracker._store.async_save.assert_not_called()


def test_corrupt_storage_is_not_overwritten(forecast_module):
    tracker = forecast_module.ConsumptionForecast(None)
    tracker._store.async_load = AsyncMock(return_value={"version": 1, "channels": {
        "chlorine": [dict(date="2026-09-01", day_seconds=86400, runtime_seconds=-1)]}})
    tracker._store.async_save = AsyncMock()
    with pytest.raises(ValueError):
        asyncio.run(tracker.async_load())
    tracker._dirty = True
    asyncio.run(tracker.async_save(force=True))
    tracker._store.async_save.assert_not_called()


def test_history_is_bounded_and_long_expired_history_not_used(forecast_module):
    tracker = forecast_module.ConsumptionForecast(None)
    seed(forecast_module, tracker, start="2025-01-01")
    assert calculate(tracker).remaining_days is None
    tracker.advance_day(datetime(2026, 9, 4, tzinfo=UTC))
    assert tracker.days["chlorine"] == {}


def test_eight_new_entities_and_translated_statuses(integration_modules):
    sensor = integration_modules["sensor"]
    descriptions = sensor.FORECAST_DESCRIPTIONS
    assert len(descriptions) == 8
    old_ids = {d.key for d in sensor.DESCRIPTIONS}
    new_ids = {d.key for d in descriptions}
    assert len(new_ids) == 8 and not old_ids & new_ids
    for filename in ("strings.json", "translations/en.json", "translations/de.json"):
        data = json.loads((Path("custom_components/aseko_asin_aqua_home") / filename).read_text(encoding="utf-8"))
        for description in descriptions:
            translation = data["entity"]["sensor"][description.key]
            assert translation["name"]
            if description.metric == "forecast_status":
                assert set(translation["state"]) == set(description.options)


def test_forecast_entities_preserve_container_state_and_explain_offline(integration_modules, forecast_module):
    sensor = integration_modules["sensor"]
    tracker = integration_modules["dosing_tracker"].DosingTracker(None, "entry")
    tracker.states["algicide"].accumulated_runtime_seconds = 7200
    forecast = forecast_module.ConsumptionForecast(None)
    coord = SimpleNamespace(dosing_tracker=tracker, forecast=forecast,
                            options={"algicide_container_size": 6, "algicide_flow_rate": 20},
                            data=SimpleNamespace(sensors={"algicide_dose": 0}),
                            data_available=True, last_valid_frame=None)
    entities = {d.metric: sensor.AsekoForecastSensor(coord, d)
                for d in sensor.FORECAST_DESCRIPTIONS if d.channel_key == "algicide"}
    before = deepcopy(tracker.as_dict())
    assert entities["remaining_days"]._attr_unique_id == "asin_aqua_home_algicide_remaining_days"
    assert entities["remaining_days"].native_value is None
    assert entities["forecast_status"].native_value == "paused"
    coord.data_available = False
    assert entities["forecast_status"].available
    assert entities["forecast_status"].native_value == "device_data_missing"
    assert entities["remaining_days"].extra_state_attributes["forecast_status"] == "device_data_missing"
    assert tracker.as_dict() == before
