"""ASEKO ASIN AQUA Home integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .const import (
    DEFAULT_FORWARD_ENABLED,
    DEFAULT_FORWARD_HOST,
    DEFAULT_FORWARD_PORT,
    DEFAULT_CAPTURE_ENABLED,
    DEFAULT_MAX_CHLORINE,
    DEFAULT_PROTOCOL_DEBUG,
    DEFAULT_LISTEN_HOST,
    DEFAULT_LISTEN_PORT,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import AsekoCoordinator


def _options(entry: ConfigEntry) -> dict:
    values = {**entry.data, **entry.options}
    return {
        "listen_host": values.get("listen_host", DEFAULT_LISTEN_HOST),
        "listen_port": values.get("listen_port", DEFAULT_LISTEN_PORT),
        "forward_enabled": values.get("forward_enabled", DEFAULT_FORWARD_ENABLED),
        "forward_host": values.get("forward_host", DEFAULT_FORWARD_HOST),
        "forward_port": values.get("forward_port", DEFAULT_FORWARD_PORT),
        "protocol_debug": values.get("protocol_debug", DEFAULT_PROTOCOL_DEBUG),
        "capture_enabled": values.get("capture_enabled", DEFAULT_CAPTURE_ENABLED),
        "max_chlorine": values.get("max_chlorine", DEFAULT_MAX_CHLORINE),
    }


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = AsekoCoordinator(hass, _options(entry))
    await coordinator.async_start()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    entry.async_on_unload(entry.add_update_listener(_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if unload := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await hass.data[DOMAIN].pop(entry.entry_id).async_stop()
    return unload


async def _reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
