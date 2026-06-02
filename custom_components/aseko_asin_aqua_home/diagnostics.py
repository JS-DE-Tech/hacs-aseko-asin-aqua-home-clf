"""Diagnostics for ASEKO ASIN AQUA Home."""

from homeassistant.components.diagnostics import async_redact_data
from .const import DOMAIN

TO_REDACT = {"listen_host", "forward_host"}


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    return {
        "config_entry": async_redact_data({**entry.data, **entry.options}, TO_REDACT),
        "connected_clients": coordinator.clients,
        "last_valid_frame": coordinator.last_valid_frame.isoformat()
        if coordinator.last_valid_frame
        else None,
        "raw_protocol_fields": coordinator.data.raw_fields
        if coordinator.data
        else None,
    }
