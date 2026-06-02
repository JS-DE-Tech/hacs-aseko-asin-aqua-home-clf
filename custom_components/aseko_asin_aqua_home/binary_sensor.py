"""Binary sensors for ASEKO ASIN AQUA Home."""

from dataclasses import dataclass
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DEVICE_IDENTIFIER, DOMAIN
from .protocol import ERROR_NAMES, RELAY_NAMES


@dataclass(frozen=True, kw_only=True)
class AsekoBinarySensorDescription(BinarySensorEntityDescription):
    source: str
    item: str


RELAY_ICONS = {
    "backwash": "mdi:backup-restore",
    "filling": "mdi:water-plus",
    "heating": "mdi:radiator",
    "filtration": "mdi:water-pump",
    "algicide": "mdi:flask-outline",
    "flocculation": "mdi:flask-outline",
    "chlorine": "mdi:water-opacity",
    "ph_minus": "mdi:ph",
}

STATUS_ICONS = {
    "filtration": "mdi:water-pump",
    "standby": "mdi:power-standby",
    "heating": "mdi:radiator",
    "open_menu": "mdi:menu-open",
}

DESCRIPTIONS = (
    [
        AsekoBinarySensorDescription(
            key=f"error_{key}",
            translation_key=f"error_{key}",
            source="errors",
            item=key,
            icon="mdi:alert-circle-outline",
            device_class=BinarySensorDeviceClass.PROBLEM,
        )
        for key in ERROR_NAMES
    ]
    + [
        AsekoBinarySensorDescription(
            key=f"relay_{key}",
            translation_key=f"relay_{key}",
            source="relays",
            item=key,
            icon=RELAY_ICONS[key],
        )
        for key in RELAY_NAMES
    ]
    + [
        AsekoBinarySensorDescription(
            key=f"status_{key}",
            translation_key=f"status_{key}",
            source="status",
            item=key,
            icon=STATUS_ICONS[key],
        )
        for key in STATUS_ICONS
    ]
)


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        AsekoBinarySensor(hass.data[DOMAIN][entry.entry_id], d) for d in DESCRIPTIONS
    )


class AsekoBinarySensor(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, description: AsekoBinarySensorDescription):
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{DEVICE_IDENTIFIER}_{description.key}"

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
            getattr(self.coordinator.data, self.entity_description.source).get(
                self.entity_description.item
            )
            if self.entity_description.source != "status"
            else getattr(self.coordinator.data.status, self.entity_description.item)
        )
