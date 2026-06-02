"""Switch entities for ASEKO ASIN AQUA Home."""

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_FORWARD_ENABLED,
    DEFAULT_FORWARD_ENABLED,
    DEVICE_IDENTIFIER,
    DOMAIN,
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up ASEKO ASIN AQUA Home switch entities."""
    async_add_entities(
        [AsekoCloudForwardingSwitch(hass.data[DOMAIN][entry.entry_id], hass, entry)]
    )


class AsekoCloudForwardingSwitch(CoordinatorEntity, SwitchEntity):
    """Enable or disable one-way ASEKO cloud forwarding."""

    _attr_has_entity_name = True
    _attr_translation_key = "cloud_forwarding"
    _attr_unique_id = "asin_aqua_home_cloud_forwarding"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
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
        return bool(
            self.entry.options.get(
                CONF_FORWARD_ENABLED,
                self.entry.data.get(CONF_FORWARD_ENABLED, DEFAULT_FORWARD_ENABLED),
            )
        )

    @property
    def icon(self) -> str:
        return "mdi:cloud-sync" if self.is_on else "mdi:cloud-off-outline"

    async def async_turn_on(self, **kwargs) -> None:
        await self._set_forwarding(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set_forwarding(False)

    async def _set_forwarding(self, enabled: bool) -> None:
        options = dict(self.entry.options)
        options[CONF_FORWARD_ENABLED] = enabled
        self.hass.config_entries.async_update_entry(self.entry, options=options)
