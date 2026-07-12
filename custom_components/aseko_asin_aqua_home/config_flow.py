"""Config flow for ASEKO ASIN AQUA Home."""

from __future__ import annotations
import voluptuous as vol
from homeassistant import config_entries
from .const import (
    CONF_CAPTURE_ENABLED,
    CONFIG_ENTRY_VERSION,
    CONF_FORWARD_ENABLED,
    CONF_FORWARD_HOST,
    CONF_FORWARD_PORT,
    CONF_LISTEN_HOST,
    CONF_LISTEN_PORT,
    CONF_MAX_CHLORINE,
    CONF_PROTOCOL_DEBUG,
    CONF_WATER_LEVEL_OFFSET,
    DEFAULT_CAPTURE_ENABLED,
    DEFAULT_FORWARD_ENABLED,
    DEFAULT_FORWARD_HOST,
    DEFAULT_FORWARD_PORT,
    DEFAULT_LISTEN_HOST,
    DEFAULT_LISTEN_PORT,
    DEFAULT_MAX_CHLORINE,
    DEFAULT_PROTOCOL_DEBUG,
    DEFAULT_WATER_LEVEL_OFFSET,
    DOMAIN,
)


def schema(values: dict | None = None):
    """Build the setup and options schema with each option declared exactly once."""
    values = values or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_LISTEN_HOST,
                default=values.get(CONF_LISTEN_HOST, DEFAULT_LISTEN_HOST),
            ): str,
            vol.Required(
                CONF_LISTEN_PORT,
                default=values.get(CONF_LISTEN_PORT, DEFAULT_LISTEN_PORT),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
            vol.Required(
                CONF_FORWARD_ENABLED,
                default=values.get(CONF_FORWARD_ENABLED, DEFAULT_FORWARD_ENABLED),
            ): bool,
            vol.Required(
                CONF_FORWARD_HOST,
                default=values.get(CONF_FORWARD_HOST, DEFAULT_FORWARD_HOST),
            ): str,
            vol.Required(
                CONF_FORWARD_PORT,
                default=values.get(CONF_FORWARD_PORT, DEFAULT_FORWARD_PORT),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
            vol.Required(
                CONF_PROTOCOL_DEBUG,
                default=values.get(CONF_PROTOCOL_DEBUG, DEFAULT_PROTOCOL_DEBUG),
            ): bool,
            vol.Required(
                CONF_CAPTURE_ENABLED,
                default=values.get(CONF_CAPTURE_ENABLED, DEFAULT_CAPTURE_ENABLED),
            ): bool,
            vol.Required(
                CONF_MAX_CHLORINE,
                default=values.get(CONF_MAX_CHLORINE, DEFAULT_MAX_CHLORINE),
            ): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=100.0)),
            vol.Required(
                CONF_WATER_LEVEL_OFFSET,
                default=values.get(
                    CONF_WATER_LEVEL_OFFSET, DEFAULT_WATER_LEVEL_OFFSET
                ),
            ): vol.All(vol.Coerce(int), vol.Range(min=-100, max=100)),
        }
    )


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = CONFIG_ENTRY_VERSION

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title="ASIN AQUA Home", data=user_input)
        return self.async_show_form(step_id="user", data_schema=schema())

    @staticmethod
    def async_get_options_flow(config_entry):
        return OptionsFlow(config_entry)


class OptionsFlow(config_entries.OptionsFlow):
    def __init__(self, entry):
        self.entry = entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=schema({**self.entry.data, **self.entry.options}),
        )
