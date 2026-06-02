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


SENSOR_ICONS = {
    "ph": "mdi:ph",
    "chlorine": "mdi:water-opacity",
    "air_temperature": "mdi:thermometer",
    "water_temperature": "mdi:thermometer-water",
    "water_level": "mdi:waves-arrow-up",
    "water_level_probe": "mdi:ruler",
    "system_date": "mdi:calendar",
    "system_time": "mdi:clock-outline",
    "time_deviation": "mdi:timer-outline",
    "set_time_recommended": "mdi:clock-alert-outline",
    "ph_target": "mdi:target",
    "chlorine_target": "mdi:target",
    "flocculation_dose": "mdi:flask-outline",
    "water_temperature_target": "mdi:thermometer-check",
    "filter_1_start": "mdi:clock-start",
    "filter_1_end": "mdi:clock-end",
    "filter_2_start": "mdi:clock-start",
    "filter_2_end": "mdi:clock-end",
    "backwash_interval_days": "mdi:calendar-sync",
    "backwash_start": "mdi:backup-restore",
    "algicide_dose": "mdi:flask-outline",
    "filling_time_limit": "mdi:timer-outline",
    "pool_volume": "mdi:pool",
    "water_level_low": "mdi:arrow-collapse-down",
    "refill_on": "mdi:water-plus",
    "refill_off": "mdi:water-minus",
    "water_level_high": "mdi:arrow-collapse-up",
    "dosing_delay": "mdi:timer-outline",
    "startup_delay": "mdi:timer-outline",
    "concentration": "mdi:percent",
    "ph_minus_concentration": "mdi:percent",
    "max_chlorine_doses": "mdi:counter",
    "max_ph_doses": "mdi:counter",
    "error_byte": "mdi:alert-circle-outline",
    "error_byte_binary": "mdi:code-braces",
    "relay_byte": "mdi:numeric",
    "relay_byte_binary": "mdi:code-braces",
    "byte24": "mdi:numeric",
    "byte24_binary": "mdi:code-braces",
    "raw_status": "mdi:state-machine",
}


def sensor_description(key: str, **kwargs) -> AsekoSensorDescription:
    return AsekoSensorDescription(
        key=key,
        translation_key=key,
        icon=SENSOR_ICONS[key],
        **kwargs,
    )


DESCRIPTIONS = [
    sensor_description("ph"),
    sensor_description(
        "chlorine",
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
    ),
    sensor_description(
        "air_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    sensor_description(
        "water_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    sensor_description(
        "water_level",
        native_unit_of_measurement="cm",
    ),
    sensor_description(
        "water_level_probe",
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
    DESCRIPTIONS.append(sensor_description(key))


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
