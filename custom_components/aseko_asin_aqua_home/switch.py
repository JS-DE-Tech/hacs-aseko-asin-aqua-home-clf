"""Switch entities for ASEKO ASIN AQUA Home."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory

from .const import (
    CONF_FORWARD_ENABLED,
    DEFAULT_FORWARD_ENABLED,
    DEVICE_IDENTIFIER,
    DOMAIN,
)

CLOUD_FORWARDING_DESCRIPTION = SwitchEntityDescription(
    key="cloud_forwarding",
    translation_key="cloud_forwarding",
    entity_category=EntityCategory.CONFIG,
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    async_add_entities([AsekoCloudForwardingSwitch(hass, entry)])


class AsekoCloudForwardingSwitch(SwitchEntity):
    """Enable or disable one-way forwarding to the ASEKO cloud."""

    _attr_has_entity_name = True
    _attr_unique_id = "asin_aqua_home_cloud_forwarding"
    _attr_suggested_object_id = "asin_aqua_home_cloud_forwarding"
    entity_description = CLOUD_FORWARDING_DESCRIPTION

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, DEVICE_IDENTIFIER)},
            "manufacturer": "ASEKO",
            "model": "ASIN AQUA Home",
            "name": "ASIN AQUA Home",
        }

    @property
    def is_on(self) -> bool:
        return self.entry.options.get(
            CONF_FORWARD_ENABLED,
            self.entry.data.get(CONF_FORWARD_ENABLED, DEFAULT_FORWARD_ENABLED),
        )

    @property
    def icon(self) -> str:
        return "mdi:cloud-sync" if self.is_on else "mdi:cloud-off-outline"

    async def async_turn_on(self, **kwargs) -> None:
        await self._set_enabled(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set_enabled(False)

    async def _set_enabled(self, enabled: bool) -> None:
        coordinator = self.hass.data[DOMAIN][self.entry.entry_id]
        await coordinator.async_set_forwarding_enabled(enabled)
        self.hass.config_entries.async_update_entry(
            self.entry,
            options={**self.entry.options, CONF_FORWARD_ENABLED: enabled},
        )
        self.async_write_ha_state()
