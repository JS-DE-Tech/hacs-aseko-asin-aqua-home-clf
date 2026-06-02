"""Number entities for ASEKO ASIN AQUA Home."""

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory

from .const import (
    CONF_WATER_LEVEL_OFFSET,
    DEFAULT_WATER_LEVEL_OFFSET,
    DEVICE_IDENTIFIER,
    DOMAIN,
)

WATER_LEVEL_OFFSET_DESCRIPTION = NumberEntityDescription(
    key=CONF_WATER_LEVEL_OFFSET,
    translation_key=CONF_WATER_LEVEL_OFFSET,
    icon="mdi:ruler",
    native_min_value=-100,
    native_max_value=100,
    native_step=1,
    native_unit_of_measurement="cm",
    mode=NumberMode.BOX,
    entity_category=EntityCategory.CONFIG,
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    async_add_entities([AsekoWaterLevelOffsetNumber(hass, entry)])


class AsekoWaterLevelOffsetNumber(NumberEntity):
    """Configure the probe-to-water-level offset in centimeters."""

    _attr_has_entity_name = True
    _attr_unique_id = "asin_aqua_home_water_level_offset"
    entity_description = WATER_LEVEL_OFFSET_DESCRIPTION

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
    def native_value(self) -> int:
        return self.entry.options.get(
            CONF_WATER_LEVEL_OFFSET,
            self.entry.data.get(CONF_WATER_LEVEL_OFFSET, DEFAULT_WATER_LEVEL_OFFSET),
        )

    async def async_set_native_value(self, value: float) -> None:
        offset = int(value)
        self.hass.config_entries.async_update_entry(
            self.entry,
            options={**self.entry.options, CONF_WATER_LEVEL_OFFSET: offset},
        )
        await self.hass.config_entries.async_reload(self.entry.entry_id)
