"""Sensors for ASEKO ASIN AQUA Home."""

from dataclasses import dataclass
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import (
    UnitOfTemperature,
    CONCENTRATION_PARTS_PER_MILLION,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DEVICE_IDENTIFIER, DOMAIN


@dataclass(frozen=True, kw_only=True)
class AsekoSensorDescription(SensorEntityDescription):
    unit: str | None = None


DESCRIPTIONS = [
    AsekoSensorDescription(key="ph", translation_key="ph"),
    AsekoSensorDescription(
        key="chlorine",
        translation_key="chlorine",
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
    ),
    AsekoSensorDescription(
        key="air_temperature",
        translation_key="air_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    AsekoSensorDescription(
        key="water_temperature",
        translation_key="water_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    AsekoSensorDescription(
        key="water_level",
        translation_key="water_level",
        native_unit_of_measurement="cm",
    ),
    AsekoSensorDescription(
        key="water_level_probe",
        translation_key="water_level_probe",
        native_unit_of_measurement="cm",
    ),
]
for key in (
    "system_date",
    "system_time",
    "time_deviation",
    "set_time_recommended",
    "ph_target",
    "chlorine_target",
    "flocculation_dose",
    "water_temperature_target",
    "filter_1_start",
    "filter_1_end",
    "filter_2_start",
    "filter_2_end",
    "backwash_interval_days",
    "backwash_start",
    "algicide_dose",
    "filling_time_limit",
    "pool_volume",
    "water_level_low",
    "refill_on",
    "refill_off",
    "water_level_high",
    "dosing_delay",
    "startup_delay",
    "concentration",
    "ph_minus_concentration",
    "max_chlorine_doses",
    "max_ph_doses",
    "error_byte",
    "error_byte_binary",
    "relay_byte",
    "relay_byte_binary",
    "byte24",
    "byte24_binary",
    "raw_status",
):
    DESCRIPTIONS.append(AsekoSensorDescription(key=key, translation_key=key))


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        AsekoSensor(hass.data[DOMAIN][entry.entry_id], d) for d in DESCRIPTIONS
    )


class AsekoSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, description):
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
    def native_value(self):
        return (
            self.coordinator.data.sensors.get(self.entity_description.key)
            if self.coordinator.data
            else None
        )
