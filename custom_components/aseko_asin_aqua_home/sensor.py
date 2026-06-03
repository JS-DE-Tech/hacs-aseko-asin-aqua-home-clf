"""Sensors for ASEKO ASIN AQUA Home."""

from dataclasses import dataclass
from datetime import datetime
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
from .const import DEFAULT_DOSING_FLOW_RATE, DEVICE_IDENTIFIER, DOMAIN
from .dosing_tracker import DOSING_CHANNELS


@dataclass(frozen=True, kw_only=True)
class AsekoSensorDescription(SensorEntityDescription):
    unit: str | None = None
    channel_key: str | None = None
    metric: str | None = None


SENSOR_ICONS = {
    "ph": "mdi:flask-outline",
    "chlorine": "mdi:flask-outline",
    "air_temperature": "mdi:sun-thermometer-outline",
    "water_temperature": "mdi:thermometer-water",
    "water_level": "mdi:waves",
    "water_level_probe": "mdi:ruler",
    "system_date": "mdi:calendar",
    "system_time": "mdi:clock-outline",
    "time_deviation": "mdi:clock-plus-outline",
    "set_time_recommended": "mdi:gesture-tap-button",
    "ph_target": "mdi:flask-outline",
    "chlorine_target": "mdi:flask-outline",
    "flocculation_dose": "mdi:bottle-tonic-outline",
    "water_temperature_target": "mdi:thermometer-check",
    "filter_1_start": "mdi:clock-start",
    "filter_1_end": "mdi:clock-end",
    "filter_2_start": "mdi:clock-start",
    "filter_2_end": "mdi:clock-end",
    "backwash_interval_days": "mdi:calendar-sync",
    "backwash_start": "mdi:recycle",
    "algicide_dose": "mdi:bottle-tonic",
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
    "last_backwash": "mdi:recycle",
}

DOSING_SENSOR_METRICS = {
    "runtime_since_replacement": {
        "icon": "mdi:timer-outline",
        "unit": "s",
        "device_class": getattr(SensorDeviceClass, "DURATION", "duration"),
    },
    "consumed_liters": {"icon": "mdi:water-minus", "unit": "l"},
    "remaining_liters": {"icon": "mdi:cup-water", "unit": "l"},
    "remaining_percent": {"icon": "mdi:gauge", "unit": "%"},
    "suggested_flow_rate": {
        "icon": "mdi:calculator-variant-outline",
        "unit": "l/h",
    },
    "last_container_replacement": {
        "icon": "mdi:calendar-refresh",
        "device_class": getattr(SensorDeviceClass, "TIMESTAMP", "timestamp"),
    },
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
    sensor_description(
        "last_backwash",
        device_class=SensorDeviceClass.TIMESTAMP,
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

for channel in DOSING_CHANNELS:
    for metric, metadata in DOSING_SENSOR_METRICS.items():
        key = f"{channel.key}_{metric}"
        DESCRIPTIONS.append(
            AsekoSensorDescription(
                key=key,
                translation_key=key,
                icon=metadata["icon"],
                native_unit_of_measurement=metadata.get("unit"),
                device_class=metadata.get("device_class"),
                channel_key=channel.key,
                metric=metric,
            )
        )


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
        self._attr_suggested_object_id = f"{DEVICE_IDENTIFIER}_{description.key}"

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
        if self.entity_description.key == "last_backwash":
            return True
        if self.entity_description.channel_key:
            if self.entity_description.metric in (
                "consumed_liters",
                "remaining_liters",
                "remaining_percent",
            ):
                return self._flow_rate() > 0
            if self.entity_description.metric == "suggested_flow_rate":
                return self._runtime_seconds() > 0
            return True
        return super().available and self.coordinator.data_available

    @property
    def native_value(self):
        if self.entity_description.channel_key:
            return self._dosing_native_value()
        if self.entity_description.key == "last_backwash":
            return self.coordinator.backwash_tracker.last_backwash
        return (
            self.coordinator.data.sensors.get(self.entity_description.key)
            if self.coordinator.data
            else None
        )

    def _runtime_seconds(self) -> float:
        return self.coordinator.dosing_tracker.states[
            self.entity_description.channel_key
        ].accumulated_runtime_seconds

    def _container_size(self) -> float:
        key = f"{self.entity_description.channel_key}_container_size"
        channel = next(
            channel
            for channel in DOSING_CHANNELS
            if channel.key == self.entity_description.channel_key
        )
        return float(self.coordinator.options.get(key, channel.container_size_default))

    def _flow_rate(self) -> float:
        key = f"{self.entity_description.channel_key}_flow_rate"
        return float(self.coordinator.options.get(key, DEFAULT_DOSING_FLOW_RATE))

    def _dosing_native_value(self):
        runtime_seconds = self._runtime_seconds()
        runtime_hours = runtime_seconds / 3600
        container_size = self._container_size()
        flow_rate = self._flow_rate()
        metric = self.entity_description.metric
        if metric == "runtime_since_replacement":
            return round(runtime_seconds)
        if metric == "last_container_replacement":
            value = self.coordinator.dosing_tracker.states[
                self.entity_description.channel_key
            ].last_container_replacement_timestamp
            return datetime.fromisoformat(value) if value else None
        if metric == "suggested_flow_rate":
            return (
                round(container_size / runtime_hours, 2)
                if runtime_hours > 0
                else None
            )
        if flow_rate <= 0:
            return None
        consumed = runtime_hours * flow_rate
        remaining = max(0, container_size - consumed)
        if metric == "consumed_liters":
            return round(consumed, 1)
        if metric == "remaining_liters":
            return round(remaining, 1)
        if metric == "remaining_percent":
            percent = max(0, min(100, remaining / container_size * 100))
            return round(percent, 1)
        return None
