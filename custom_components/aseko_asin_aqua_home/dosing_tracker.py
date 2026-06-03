"""Persistent dosing pump runtime tracking for ASEKO ASIN AQUA Home."""

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
MAX_COUNTABLE_INTERVAL_SECONDS = 60
SAVE_INTERVAL_SECONDS = 45
STABLE_STORAGE_KEY = "aseko_asin_aqua_home_dosing_tracker"


@dataclass(frozen=True, slots=True)
class DosingChannelDescription:
    """Static metadata for one chemical dosing channel."""

    key: str
    relay_key: str
    container_size_default: float
    german_prefix: str
    english_prefix: str


DOSING_CHANNELS: tuple[DosingChannelDescription, ...] = (
    DosingChannelDescription("chlorine", "chlorine", 20.0, "Chlor", "Chlorine"),
    DosingChannelDescription("ph_minus", "ph_minus", 20.0, "pH-Minus", "pH-Minus"),
    DosingChannelDescription(
        "flocculation", "flocculation", 6.0, "Flockungsmittel", "Flocculation"
    ),
    DosingChannelDescription("algicide", "algicide", 6.0, "Algizid", "Algicide"),
)
DOSING_CHANNELS_BY_KEY = {channel.key: channel for channel in DOSING_CHANNELS}


@dataclass(slots=True)
class DosingChannelState:
    """Runtime state persisted for one dosing channel."""

    accumulated_runtime_seconds: float = 0.0
    last_relay_state: bool = False
    last_observed_timestamp: str | None = None
    last_container_replacement_timestamp: str | None = None
    last_calculated_flow_rate: float | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> DosingChannelState:
        if not isinstance(data, dict):
            return cls()
        return cls(
            accumulated_runtime_seconds=float(
                data.get("accumulated_runtime_seconds", 0.0)
            ),
            last_relay_state=bool(data.get("last_relay_state", False)),
            last_observed_timestamp=data.get("last_observed_timestamp"),
            last_container_replacement_timestamp=data.get(
                "last_container_replacement_timestamp"
            ),
            last_calculated_flow_rate=(
                float(data["last_calculated_flow_rate"])
                if data.get("last_calculated_flow_rate") is not None
                else None
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "accumulated_runtime_seconds": self.accumulated_runtime_seconds,
            "last_relay_state": self.last_relay_state,
            "last_observed_timestamp": self.last_observed_timestamp,
            "last_container_replacement_timestamp": self.last_container_replacement_timestamp,
            "last_calculated_flow_rate": self.last_calculated_flow_rate,
        }


class DosingTracker:
    """Track pump runtime from valid relay observations and persist it.

    The tracker only counts the interval between consecutive valid decoded payloads
    when the previous relay state was active. A single interval is ignored when it is
    longer than ``MAX_COUNTABLE_INTERVAL_SECONDS`` so outages, reloads, disconnected
    gateways, and clock corrections do not create unbounded chemical consumption.
    """

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self.store_key = STABLE_STORAGE_KEY
        self._store = Store(hass, STORAGE_MAJOR_VERSION, self.store_key)
        self._legacy_store = Store(
            hass, STORAGE_MAJOR_VERSION, f"{STABLE_STORAGE_KEY}_{entry_id}"
        )
        self.states = {channel.key: DosingChannelState() for channel in DOSING_CHANNELS}
        self._dirty = False
        self._last_save_timestamp: datetime | None = None

    async def async_load(self) -> None:
        data = await self._store.async_load()
        migrated = False
        if not data:
            data = await self._legacy_store.async_load()
            migrated = data is not None
        if not data:
            return
        if data.get("version", STORAGE_VERSION) > STORAGE_VERSION:
            _LOGGER.warning("Ignoring newer dosing tracker storage version")
            return
        channels = data.get("channels", {})
        for channel in DOSING_CHANNELS:
            self.states[channel.key] = DosingChannelState.from_dict(
                channels.get(channel.key)
            )
        if migrated:
            await self.async_save()

    def observe_relays(
        self, relays: dict[str, bool], now: datetime | None = None
    ) -> bool:
        """Update runtime state from one valid decoded payload.

        Return ``True`` when a relay transition should be persisted immediately.
        """
        now = now or datetime.now(timezone.utc)
        now_iso = now.isoformat()
        save_needed = False
        transition_seen = False
        for channel in DOSING_CHANNELS:
            state = self.states[channel.key]
            previous_timestamp = _parse_datetime(state.last_observed_timestamp)
            if previous_timestamp is not None:
                elapsed = (now - previous_timestamp).total_seconds()
                if (
                    state.last_relay_state
                    and 0 < elapsed <= MAX_COUNTABLE_INTERVAL_SECONDS
                ):
                    state.accumulated_runtime_seconds += elapsed
                    self._dirty = True
                    if elapsed > 0:
                        save_needed = True
            relay_state = bool(relays.get(channel.relay_key, False))
            if relay_state != state.last_relay_state:
                save_needed = True
                transition_seen = True
                self._dirty = True
            state.last_relay_state = relay_state
            state.last_observed_timestamp = now_iso
        if save_needed:
            self._dirty = True
        return transition_seen

    async def async_maybe_save(self, now: datetime | None = None) -> None:
        if not self._dirty:
            return
        now = now or datetime.now(timezone.utc)
        if (
            self._last_save_timestamp is not None
            and (now - self._last_save_timestamp).total_seconds()
            < SAVE_INTERVAL_SECONDS
        ):
            return
        await self.async_save()

    async def async_save(self) -> None:
        await self._store.async_save(self.as_dict())
        self._dirty = False
        self._last_save_timestamp = datetime.now(timezone.utc)

    async def async_store_calculated_flow_rate(
        self, channel_key: str, flow_rate: float
    ) -> None:
        """Persist the last accepted calculated pump flow rate."""
        self.states[channel_key].last_calculated_flow_rate = flow_rate
        self._dirty = True
        await self.async_save()

    async def async_reset_container(self, channel_key: str) -> None:
        state = self.states[channel_key]
        reset_timestamp = datetime.now(timezone.utc).isoformat()
        state.accumulated_runtime_seconds = 0.0
        state.last_observed_timestamp = reset_timestamp
        state.last_container_replacement_timestamp = reset_timestamp
        self._dirty = True
        await self.async_save()

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": STORAGE_VERSION,
            "channels": {key: state.as_dict() for key, state in self.states.items()},
        }


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
