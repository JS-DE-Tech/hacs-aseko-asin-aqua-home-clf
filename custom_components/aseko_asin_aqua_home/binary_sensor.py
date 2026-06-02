"""Binary sensors for ASEKO ASIN AQUA Home."""

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DEVICE_IDENTIFIER, DOMAIN
from .protocol import ERROR_NAMES, RELAY_NAMES

DESCRIPTIONS = (
    [(f"error_{key}", "errors", key) for key in ERROR_NAMES]
    + [(f"relay_{key}", "relays", key) for key in RELAY_NAMES]
    + [
        (f"status_{key}", "status", key)
        for key in ("filtration", "standby", "heating", "open_menu")
    ]
)


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        AsekoBinarySensor(hass.data[DOMAIN][entry.entry_id], *d) for d in DESCRIPTIONS
    )


class AsekoBinarySensor(CoordinatorEntity, BinarySensorEntity):
    def __init__(self, coordinator, key, source, item):
        super().__init__(coordinator)
        self.entity_description = BinarySensorEntityDescription(
            key=key, translation_key=key
        )
        self.source = source
        self.item = item
        self._attr_unique_id = f"{DEVICE_IDENTIFIER}_{key}"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, DEVICE_IDENTIFIER)},
            "manufacturer": "ASEKO",
            "model": "ASIN AQUA Home",
            "name": "ASIN AQUA Home",
        }

    @property
    def available(self):
        return super().available and self.coordinator.data_available

    @property
    def is_on(self):
        if not self.coordinator.data:
            return None
        return (
            getattr(self.coordinator.data, self.source).get(self.item)
            if self.source != "status"
            else getattr(self.coordinator.data.status, self.item)
        )
