"""Number entities for ASEKO ASIN AQUA Home."""

from __future__ import annotations

from dataclasses import dataclass

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
    DEFAULT_DOSING_FLOW_RATE,
    DEFAULT_WATER_LEVEL_OFFSET,
    DEVICE_IDENTIFIER,
    DOMAIN,
)
from .dosing_tracker import DOSING_CHANNELS, DosingChannelDescription


@dataclass(frozen=True, kw_only=True)
class AsekoNumberDescription(NumberEntityDescription):
    """Number entity description with config option metadata."""

    default_value: float


WATER_LEVEL_OFFSET_DESCRIPTION = AsekoNumberDescription(
    key=CONF_WATER_LEVEL_OFFSET,
    translation_key=CONF_WATER_LEVEL_OFFSET,
    icon="mdi:ruler",
    native_min_value=-100,
    native_max_value=100,
    native_step=1,
    native_unit_of_measurement="cm",
    mode=NumberMode.BOX,
    entity_category=EntityCategory.CONFIG,
    default_value=DEFAULT_WATER_LEVEL_OFFSET,
)


def _container_size_description(
    channel: DosingChannelDescription,
) -> AsekoNumberDescription:
    key = f"{channel.key}_container_size"
    return AsekoNumberDescription(
        key=key,
        translation_key=key,
        icon="mdi:cup-water",
        native_min_value=0.1,
        native_max_value=100.0,
        native_step=0.1,
        native_unit_of_measurement="l",
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        default_value=channel.container_size_default,
    )


def _flow_rate_description(
    channel: DosingChannelDescription,
) -> AsekoNumberDescription:
    key = f"{channel.key}_flow_rate"
    return AsekoNumberDescription(
        key=key,
        translation_key=key,
        icon="mdi:pump",
        native_min_value=0.0,
        native_max_value=20.0,
        native_step=0.01,
        native_unit_of_measurement="l/h",
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        default_value=DEFAULT_DOSING_FLOW_RATE,
    )


DOSING_NUMBER_DESCRIPTIONS = tuple(
    description
    for channel in DOSING_CHANNELS
    for description in (
        _container_size_description(channel),
        _flow_rate_description(channel),
    )
)
DESCRIPTIONS = (WATER_LEVEL_OFFSET_DESCRIPTION, *DOSING_NUMBER_DESCRIPTIONS)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    async_add_entities(
        AsekoConfigNumber(hass, entry, description) for description in DESCRIPTIONS
    )


class AsekoConfigNumber(NumberEntity):
    """Editable numeric integration option."""

    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        description: AsekoNumberDescription,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.entity_description = description
        self._attr_unique_id = f"asin_aqua_home_{description.key}"

    @property
    def suggested_object_id(self) -> str:
        return f"asin_aqua_home_{self.entity_description.key}"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, DEVICE_IDENTIFIER)},
            "manufacturer": "ASEKO",
            "model": "ASIN AQUA Home",
            "name": "ASIN AQUA Home",
        }

    @property
    def native_value(self) -> float:
        return self.entry.options.get(
            self.entity_description.key,
            self.entry.data.get(
                self.entity_description.key,
                self.entity_description.default_value,
            ),
        )

    async def async_set_native_value(self, value: float) -> None:
        if self.entity_description.native_step == 1:
            stored_value: float | int = int(value)
        else:
            stored_value = float(value)
        self.hass.config_entries.async_update_entry(
            self.entry,
            options={**self.entry.options, self.entity_description.key: stored_value},
        )
        self.async_write_ha_state()


class AsekoWaterLevelOffsetNumber(AsekoConfigNumber):
    """Backward-compatible water-level offset entity class."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry, WATER_LEVEL_OFFSET_DESCRIPTION)
