"""Button entities for ASEKO ASIN AQUA Home."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory

from .const import (
    DEVICE_IDENTIFIER,
    DOMAIN,
    MAX_DOSING_FLOW_RATE,
    MIN_DOSING_FLOW_RATE,
)
from .dosing_tracker import DOSING_CHANNELS, DOSING_CHANNELS_BY_KEY

CONTAINER_REPLACED_BUTTON_DESCRIPTIONS = tuple(
    ButtonEntityDescription(
        key=f"{channel.key}_container_replaced",
        translation_key=f"{channel.key}_container_replaced",
        icon="mdi:refresh",
        entity_category=EntityCategory.CONFIG,
    )
    for channel in DOSING_CHANNELS
)

CALCULATE_FLOW_RATE_BUTTON_DESCRIPTIONS = tuple(
    ButtonEntityDescription(
        key=f"{channel.key}_calculate_flow_rate",
        translation_key=f"{channel.key}_calculate_flow_rate",
        icon="mdi:calculator-variant-outline",
        entity_category=EntityCategory.CONFIG,
    )
    for channel in DOSING_CHANNELS
)

BUTTON_DESCRIPTIONS = (
    *CONTAINER_REPLACED_BUTTON_DESCRIPTIONS,
    *CALCULATE_FLOW_RATE_BUTTON_DESCRIPTIONS,
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        _button_entity(hass, entry, coordinator, description)
        for description in BUTTON_DESCRIPTIONS
    )


def _button_entity(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator,
    description: ButtonEntityDescription,
) -> AsekoDosingButton:
    if description.key.endswith("_calculate_flow_rate"):
        return AsekoCalculateFlowRateButton(hass, entry, coordinator, description)
    return AsekoContainerReplacedButton(coordinator, description)


class AsekoDosingButton(ButtonEntity):
    """Base button for one dosing channel."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, description: ButtonEntityDescription) -> None:
        self.coordinator = coordinator
        self.entity_description = description
        self._attr_unique_id = f"asin_aqua_home_{description.key}"

    @property
    def suggested_object_id(self) -> str:
        return self.entity_description.key

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, DEVICE_IDENTIFIER)},
            "manufacturer": "ASEKO",
            "model": "ASIN AQUA Home",
            "name": "ASIN AQUA Home",
        }


class AsekoContainerReplacedButton(AsekoDosingButton):
    """Reset one dosing channel after a container replacement."""

    def __init__(self, coordinator, description: ButtonEntityDescription) -> None:
        super().__init__(coordinator, description)
        self._channel_key = description.key.removesuffix("_container_replaced")

    async def async_press(self) -> None:
        await self.coordinator.dosing_tracker.async_reset_container(self._channel_key)
        self.coordinator.async_update_listeners()


class AsekoCalculateFlowRateButton(AsekoDosingButton):
    """Calculate and persist a pump flow rate after an empty container."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator,
        description: ButtonEntityDescription,
    ) -> None:
        super().__init__(coordinator, description)
        self.hass = hass
        self.entry = entry
        self._channel_key = description.key.removesuffix("_calculate_flow_rate")

    async def async_press(self) -> None:
        runtime_seconds = self.coordinator.dosing_tracker.states[
            self._channel_key
        ].accumulated_runtime_seconds
        if runtime_seconds <= 0:
            raise HomeAssistantError(
                "Cannot calculate dosing pump flow rate with zero runtime"
            )

        container_size = self._container_size()
        flow_rate = round(container_size / (runtime_seconds / 3600), 2)
        if not MIN_DOSING_FLOW_RATE < flow_rate <= MAX_DOSING_FLOW_RATE:
            raise HomeAssistantError(
                "Calculated dosing pump flow rate is outside the allowed range"
            )

        flow_rate_key = f"{self._channel_key}_flow_rate"
        self.hass.config_entries.async_update_entry(
            self.entry,
            options={**self.entry.options, flow_rate_key: flow_rate},
        )
        self.coordinator.options[flow_rate_key] = flow_rate
        await self.coordinator.dosing_tracker.async_store_calculated_flow_rate(
            self._channel_key, flow_rate
        )
        self.coordinator.async_update_listeners()

    def _container_size(self) -> float:
        key = f"{self._channel_key}_container_size"
        channel = DOSING_CHANNELS_BY_KEY[self._channel_key]
        return float(
            self.coordinator.options.get(
                key,
                self.entry.options.get(
                    key,
                    self.entry.data.get(key, channel.container_size_default),
                ),
            )
        )
