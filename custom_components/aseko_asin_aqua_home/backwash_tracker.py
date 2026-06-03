"""Persistent Last Backwash tracker for ASEKO ASIN AQUA Home."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
STORAGE_MAJOR_VERSION = 1
BACKWASH_CONFIRMATION_SECONDS = 60
MAX_BACKWASH_OBSERVATION_GAP_SECONDS = 60


@dataclass(slots=True)
class BackwashTrackerState:
    """Persisted backwash detection state."""

    last_backwash_timestamp: str | None = None
    active_since_timestamp: str | None = None
    last_relay_state: bool = False
    last_observed_timestamp: str | None = None
    event_recorded_for_current_cycle: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> BackwashTrackerState:
        if not isinstance(data, dict):
            return cls()
        return cls(
            last_backwash_timestamp=data.get("last_backwash_timestamp"),
            active_since_timestamp=data.get("active_since_timestamp"),
            last_relay_state=bool(data.get("last_relay_state", False)),
            last_observed_timestamp=data.get("last_observed_timestamp"),
            event_recorded_for_current_cycle=bool(
                data.get("event_recorded_for_current_cycle", False)
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "last_backwash_timestamp": self.last_backwash_timestamp,
            "active_since_timestamp": self.active_since_timestamp,
            "last_relay_state": self.last_relay_state,
            "last_observed_timestamp": self.last_observed_timestamp,
            "event_recorded_for_current_cycle": self.event_recorded_for_current_cycle,
        }


class BackwashTracker:
    """Confirm and persist the most recent real backwash cycle.

    Only intervals between consecutive valid decoded ASEKO payloads are treated as
    continuously observed relay activity. If the gap is too large, the pending
    active observation is restarted from the current payload timestamp so a Home
    Assistant restart, reload, network outage, gateway disconnect, or clock change
    cannot create a false 60-second backwash event from an unobserved interval.
    """

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self.store_key = f"aseko_asin_aqua_home_backwash_tracker_{entry_id}"
        self._store = Store(hass, STORAGE_MAJOR_VERSION, self.store_key)
        self.state = BackwashTrackerState()
        self._dirty = False

    @property
    def last_backwash(self) -> datetime | None:
        """Return the last confirmed backwash timestamp as an aware datetime."""
        return _parse_datetime(self.state.last_backwash_timestamp)

    async def async_load(self) -> None:
        data = await self._store.async_load()
        if not data:
            return
        if data.get("version", STORAGE_VERSION) > STORAGE_VERSION:
            _LOGGER.warning("Ignoring newer backwash tracker storage version")
            return
        self.state = BackwashTrackerState.from_dict(data.get("state", data))

    def observe_relay(self, relay_active: bool, now: datetime | None = None) -> bool:
        """Observe one validated decoded backwash relay value.

        Return ``True`` when a new confirmed backwash event was recorded and must
        be persisted immediately.
        """
        now = _ensure_aware(now or datetime.now(timezone.utc))
        now_iso = now.isoformat()
        previous_observed = _parse_datetime(self.state.last_observed_timestamp)
        active_since = _parse_datetime(self.state.active_since_timestamp)
        save_needed = False
        event_confirmed = False

        gap_seconds = (
            (now - previous_observed).total_seconds()
            if previous_observed is not None
            else None
        )
        observation_gap_broken = (
            gap_seconds is not None
            and (gap_seconds <= 0 or gap_seconds > MAX_BACKWASH_OBSERVATION_GAP_SECONDS)
        )

        if relay_active:
            if not self.state.last_relay_state or active_since is None:
                active_since = now
                self.state.active_since_timestamp = now_iso
                self.state.event_recorded_for_current_cycle = False
                save_needed = True
            elif observation_gap_broken:
                # Do not count unobserved time as continuous relay activity.
                active_since = now
                self.state.active_since_timestamp = now_iso
                self.state.event_recorded_for_current_cycle = False
                save_needed = True

            if (
                active_since is not None
                and not self.state.event_recorded_for_current_cycle
                and (now - active_since).total_seconds()
                >= BACKWASH_CONFIRMATION_SECONDS
            ):
                self.state.last_backwash_timestamp = active_since.isoformat()
                self.state.event_recorded_for_current_cycle = True
                save_needed = True
                event_confirmed = True
        else:
            if self.state.last_relay_state or self.state.active_since_timestamp:
                self.state.active_since_timestamp = None
                self.state.event_recorded_for_current_cycle = False
                save_needed = True

        if relay_active != self.state.last_relay_state:
            save_needed = True
        self.state.last_relay_state = relay_active
        self.state.last_observed_timestamp = now_iso
        if save_needed:
            self._dirty = True
        return event_confirmed

    async def async_save(self) -> None:
        await self._store.async_save(self.as_dict())
        self._dirty = False

    async def async_save_if_dirty(self) -> None:
        if self._dirty:
            await self.async_save()

    def as_dict(self) -> dict[str, Any]:
        return {"version": STORAGE_VERSION, "state": self.state.as_dict()}


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    return _ensure_aware(parsed)
