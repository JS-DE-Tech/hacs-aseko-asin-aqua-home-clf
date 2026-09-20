"""Independent, persistent consumption history and conservative forecasts.

Only intervals between valid frames count as observed time. Pump runtime is kept
in seconds so recalibration behaves like the existing container calculations.
This store never modifies the dosing tracker, calibration, or entity registry.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
import math

from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .dosing_tracker import DOSING_CHANNELS, MAX_COUNTABLE_INTERVAL_SECONDS

STORAGE_KEY = "aseko_asin_aqua_home_forecast"
STORAGE_VERSION = 1
HISTORY_DAYS = 180
WINDOW_DAYS = 14
MIN_SAMPLE_DAYS = 3
MIN_COVERAGE = 0.90
MIN_ACTIVE_SECONDS = 6 * 3600
SAVE_INTERVAL_SECONDS = 45
DOSE_KEYS = {"flocculation": "flocculation_dose", "algicide": "algicide_dose"}
FORECAST_STATUSES = (
    "active", "provisional", "paused", "learning", "calibration_missing",
    "no_consumption", "insufficient_data", "device_data_missing",
)


@dataclass
class Day:
    """Observed wall time, enabled time, and enabled pump runtime per local day."""

    date: str
    day_seconds: float
    observed_seconds: float = 0.0
    active_seconds: float = 0.0
    runtime_seconds: float = 0.0


@dataclass(frozen=True)
class Forecast:
    status: str
    remaining_days: int | None = None
    daily_consumption_ml: float | None = None
    sample_days: int = 0
    last_sample_date: str | None = None


class ConsumptionForecast:
    def __init__(self, hass) -> None:
        self._store = Store(hass, 1, STORAGE_KEY)
        self.days: dict[str, dict[str, Day]] = {c.key: {} for c in DOSING_CHANNELS}
        self.started_on: str | None = None
        self._last_observed: datetime | None = None
        self._previous_relays: dict[str, bool] = {}
        self._previous_enabled: dict[str, bool | None] = {}
        self._dirty = False
        self._storage_writable = True
        self._last_saved: datetime | None = None

    async def async_load(self) -> None:
        self._storage_writable = False
        data = await self._store.async_load()
        if data is not None:
            if data.get("version") != STORAGE_VERSION:
                raise ValueError("Unsupported forecast storage version; preserving stored data")
            started = data.get("started_on")
            if started is not None:
                date.fromisoformat(started)
            restored = {c.key: {} for c in DOSING_CHANNELS}
            for channel in DOSING_CHANNELS:
                for values in data.get("channels", {}).get(channel.key, []):
                    day = Day(**values)
                    date.fromisoformat(day.date)
                    numbers = (day.runtime_seconds, day.active_seconds,
                               day.observed_seconds, day.day_seconds)
                    if (not all(math.isfinite(n) for n in numbers)
                            or not 0 <= numbers[0] <= numbers[1] <= numbers[2] <= numbers[3]
                            or not 0 < day.day_seconds <= 90000):
                        raise ValueError("Invalid forecast history; preserving stored data")
                    restored[channel.key][day.date] = day
            self.days = restored
            self.started_on = started
        self._storage_writable = True
        # Do not count downtime or infer the controller's current pause state.
        self.break_observation()

    def break_observation(self) -> None:
        """End continuity at disconnect/reload without deleting learned history."""
        self._last_observed = None
        self._previous_relays = {}
        self._previous_enabled = {}

    @staticmethod
    def enabled(channel: str, sensors: dict) -> bool | None:
        if channel not in DOSE_KEYS:
            return True
        value = sensors.get(DOSE_KEYS[channel])
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            return None
        return value > 0

    def observe(self, relays: dict, sensors: dict, now: datetime) -> None:
        now = now.astimezone(timezone.utc)
        # Ignore backwards/equal timestamps without rewinding the high-water mark.
        if self._last_observed is not None and now <= self._last_observed:
            return
        self.advance_day(now)
        if self.started_on is None:
            self.started_on = _local_date(now)
            self._dirty = True
        previous = self._last_observed
        enabled = {c.key: self.enabled(c.key, sensors) for c in DOSING_CHANNELS}
        if previous is not None and (now - previous).total_seconds() <= MAX_COUNTABLE_INTERVAL_SECONDS:
            for start, end in _split_days(previous, now):
                seconds = (end - start).total_seconds()
                day_key = _local_date(start)
                for channel in DOSING_CHANNELS:
                    was_enabled = self._previous_enabled.get(channel.key)
                    if was_enabled is None:
                        continue
                    day = self.days[channel.key].setdefault(
                        day_key, Day(day_key, _day_seconds(start))
                    )
                    # Clamping also prevents duplicate accounting after clock jumps.
                    counted = min(seconds, max(0.0, day.day_seconds - day.observed_seconds))
                    day.observed_seconds += counted
                    if was_enabled:
                        day.active_seconds += counted
                        if self._previous_relays.get(channel.relay_key, False):
                            day.runtime_seconds += counted
                    self._dirty = True
        self._last_observed = now
        self._previous_relays = dict(relays)
        self._previous_enabled = enabled

    def advance_day(self, now: datetime) -> None:
        """Completed days are selected by date, without inventing missing samples."""
        cutoff = (dt_util.as_local(now).date() - timedelta(days=HISTORY_DAYS)).isoformat()
        for days in self.days.values():
            expired = [key for key in days if key < cutoff]
            for key in expired:
                del days[key]
                self._dirty = True

    def calculate(self, channel: str, *, remaining_liters: float,
                  flow_rate_ml_min: float, sensors: dict, data_available: bool,
                  now: datetime | None = None) -> Forecast:
        now = now or datetime.now(timezone.utc)
        enabled = self.enabled(channel, sensors)
        if not data_available or enabled is None:
            return Forecast("device_data_missing")
        if not enabled:
            return Forecast("paused")
        if not math.isfinite(flow_rate_ml_min) or flow_rate_ml_min <= 0:
            return Forecast("calibration_missing")
        today = dt_util.as_local(now).date()
        cutoff = (today - timedelta(days=HISTORY_DAYS)).isoformat()
        # Fully paused days do not dilute the window; poorly observed active days
        # still occupy it so stale good samples cannot hide recent data loss.
        candidates = sorted(
            (day for day in self.days[channel].values()
             if cutoff <= day.date < today.isoformat() and day.active_seconds > 0),
            key=lambda day: day.date,
        )[-WINDOW_DAYS:]
        samples = [day for day in candidates
                   if day.observed_seconds >= day.day_seconds * MIN_COVERAGE
                   and day.active_seconds >= MIN_ACTIVE_SECONDS]
        count = len(samples)
        last_date = samples[-1].date if samples else None
        if count < MIN_SAMPLE_DAYS:
            elapsed = (today - date.fromisoformat(self.started_on)).days if self.started_on else 0
            status = "learning" if elapsed < MIN_SAMPLE_DAYS else "insufficient_data"
            return Forecast(status, sample_days=count, last_sample_date=last_date)
        # The last seven usable active days get twice the weight. Normalize to an
        # enabled 24-hour day; disabled portions of mixed days aren't zero usage.
        weighted_runtime = weighted_active = 0.0
        for index, day in enumerate(samples):
            weight = 2 if index >= count - 7 else 1
            weighted_runtime += day.runtime_seconds * weight
            weighted_active += day.active_seconds * weight
        daily_ml = weighted_runtime / weighted_active * 86400 * flow_rate_ml_min / 60
        if daily_ml <= 0:
            return Forecast("no_consumption", daily_consumption_ml=0.0,
                            sample_days=count, last_sample_date=last_date)
        # Require three recent samples before calling a resumed forecast reliable.
        recent_cutoff = (today - timedelta(days=7)).isoformat()
        recent = sum(day.date >= recent_cutoff for day in samples)
        status = "active" if recent >= MIN_SAMPLE_DAYS else "provisional"
        if len(candidates) >= MIN_SAMPLE_DAYS and len(samples) < len(candidates) * MIN_COVERAGE:
            status = "provisional"
        remaining = max(0.0, remaining_liters)
        # Floor is conservative; zero means less than one full day (or empty).
        return Forecast(status, math.floor(remaining * 1000 / daily_ml),
                        round(daily_ml, 2), count, last_date)

    async def async_save(self, *, force: bool = False, now: datetime | None = None) -> None:
        if not self._storage_writable or not self._dirty:
            return
        now = now or datetime.now(timezone.utc)
        if not force and self._last_saved and (now - self._last_saved).total_seconds() < SAVE_INTERVAL_SECONDS:
            return
        await self._store.async_save({
            "version": STORAGE_VERSION,
            "started_on": self.started_on,
            "channels": {key: [asdict(day) for day in sorted(days.values(), key=lambda d: d.date)]
                         for key, days in self.days.items()},
        })
        self._last_saved = now
        self._dirty = False


def _local_date(now: datetime) -> str:
    return dt_util.as_local(now).date().isoformat()


def _next_midnight(now: datetime) -> datetime:
    local = dt_util.as_local(now)
    return datetime.combine(local.date() + timedelta(days=1), time.min,
                            tzinfo=local.tzinfo).astimezone(timezone.utc)


def _day_seconds(now: datetime) -> float:
    local = dt_util.as_local(now)
    start = datetime.combine(local.date(), time.min, tzinfo=local.tzinfo)
    return (_next_midnight(now) - start.astimezone(timezone.utc)).total_seconds()


def _split_days(start: datetime, end: datetime):
    while start < end:
        boundary = min(end, _next_midnight(start))
        yield start, boundary
        start = boundary
