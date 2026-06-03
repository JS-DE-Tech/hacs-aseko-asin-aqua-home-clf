"""Button entities for ASEKO ASIN AQUA Home."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory

from .const import DEVICE_IDENTIFIER, DOMAIN
from .dosing_tracker import DOSING_CHANNELS

BUTTON_DESCRIPTIONS = tuple(
    ButtonEntityDescription(
        key=f"{channel.key}_container_replaced",
        translation_key=f"{channel.key}_container_replaced",
        icon="mdi:refresh",
        entity_category=EntityCategory.CONFIG,
    )
    for channel in DOSING_CHANNELS
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        AsekoContainerReplacedButton(coordinator, description)
        for description in BUTTON_DESCRIPTIONS
    )


class AsekoContainerReplacedButton(ButtonEntity):
    """Reset one dosing channel after a container replacement."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, description: ButtonEntityDescription) -> None:
        self.coordinator = coordinator
        self.entity_description = description
        self._channel_key = description.key.removesuffix("_container_replaced")
        self._attr_unique_id = f"asin_aqua_home_{description.key}"
        self._attr_suggested_object_id = f"asin_aqua_home_{description.key}"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, DEVICE_IDENTIFIER)},
            "manufacturer": "ASEKO",
            "model": "ASIN AQUA Home",
            "name": "ASIN AQUA Home",
        }

    async def async_press(self) -> None:
        await self.coordinator.dosing_tracker.async_reset_container(self._channel_key)
        self.coordinator.async_update_listeners()
