import importlib.util
from pathlib import Path
import sys
import types
from dataclasses import dataclass

import asyncio

import pytest

PACKAGE = "aseko_entity_test"
BASE = Path("custom_components/aseko_asin_aqua_home")


def install_homeassistant_stubs(monkeypatch):
    homeassistant = types.ModuleType("homeassistant")
    components = types.ModuleType("homeassistant.components")
    sensor = types.ModuleType("homeassistant.components.sensor")
    binary_sensor = types.ModuleType("homeassistant.components.binary_sensor")
    number = types.ModuleType("homeassistant.components.number")
    switch = types.ModuleType("homeassistant.components.switch")
    const = types.ModuleType("homeassistant.const")
    helpers = types.ModuleType("homeassistant.helpers")
    update_coordinator = types.ModuleType("homeassistant.helpers.update_coordinator")
    entity = types.ModuleType("homeassistant.helpers.entity")
    config_entries = types.ModuleType("homeassistant.config_entries")
    core = types.ModuleType("homeassistant.core")

    @dataclass(frozen=True, kw_only=True)
    class EntityDescription:
        key: str
        translation_key: str | None = None
        icon: str | None = None
        device_class: str | None = None
        native_unit_of_measurement: str | None = None
        native_min_value: int | None = None
        native_max_value: int | None = None
        native_step: int | None = None
        mode: str | None = None
        entity_category: str | None = None

    class SensorDeviceClass:
        TEMPERATURE = "temperature"

    class BinarySensorDeviceClass:
        PROBLEM = "problem"

    class NumberMode:
        BOX = "box"

    class EntityCategory:
        CONFIG = "config"

    class Entity:
        pass

    class CoordinatorEntity:
        def __init__(self, coordinator):
            self.coordinator = coordinator

        @property
        def available(self):
            return True

    sensor.SensorDeviceClass = SensorDeviceClass
    sensor.SensorEntity = Entity
    sensor.SensorEntityDescription = EntityDescription
    binary_sensor.BinarySensorDeviceClass = BinarySensorDeviceClass
    binary_sensor.BinarySensorEntity = Entity
    binary_sensor.BinarySensorEntityDescription = EntityDescription
    number.NumberEntity = Entity
    number.NumberEntityDescription = EntityDescription
    number.NumberMode = NumberMode
    switch.SwitchEntity = Entity
    const.UnitOfTemperature = types.SimpleNamespace(CELSIUS="°C")
    const.CONCENTRATION_PARTS_PER_MILLION = "ppm"
    entity.EntityCategory = EntityCategory
    update_coordinator.CoordinatorEntity = CoordinatorEntity
    config_entries.ConfigEntry = object
    core.HomeAssistant = object

    modules = {
        "homeassistant": homeassistant,
        "homeassistant.components": components,
        "homeassistant.components.sensor": sensor,
        "homeassistant.components.binary_sensor": binary_sensor,
        "homeassistant.components.number": number,
        "homeassistant.components.switch": switch,
        "homeassistant.const": const,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.update_coordinator": update_coordinator,
        "homeassistant.helpers.entity": entity,
        "homeassistant.config_entries": config_entries,
        "homeassistant.core": core,
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)


@pytest.fixture
def integration_modules(monkeypatch):
    install_homeassistant_stubs(monkeypatch)
    package = types.ModuleType(PACKAGE)
    package.__path__ = [str(BASE)]
    monkeypatch.setitem(sys.modules, PACKAGE, package)

    loaded = {}
    for module_name in (
        "const",
        "protocol",
        "sensor",
        "binary_sensor",
        "number",
        "switch",
    ):
        spec = importlib.util.spec_from_file_location(
            f"{PACKAGE}.{module_name}", BASE / f"{module_name}.py"
        )
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, spec.name, module)
        spec.loader.exec_module(module)
        loaded[module_name] = module
    return loaded


def test_number_platform_included_in_platforms(integration_modules):
    assert integration_modules["const"].PLATFORMS == [
        "sensor",
        "binary_sensor",
        "number",
        "switch",
    ]


def test_water_level_offset_number_range_and_default(integration_modules):
    number = integration_modules["number"]
    description = number.WATER_LEVEL_OFFSET_DESCRIPTION
    assert description.native_min_value == -100
    assert description.native_max_value == 100
    assert description.native_step == 1
    assert description.native_unit_of_measurement == "cm"
    assert description.icon == "mdi:ruler"
    assert description.mode == "box"
    assert description.entity_category == "config"

    entry = types.SimpleNamespace(data={}, options={}, entry_id="entry-1")
    entity = number.AsekoWaterLevelOffsetNumber(types.SimpleNamespace(), entry)
    assert entity.native_value == 33


def test_water_level_offset_number_updates_options_and_reloads(integration_modules):
    number = integration_modules["number"]
    calls = []

    class ConfigEntries:
        def async_update_entry(self, entry, *, options):
            calls.append(("update", options))
            entry.options = options

        async def async_reload(self, entry_id):
            calls.append(("reload", entry_id))

    entry = types.SimpleNamespace(
        data={"listen_host": "0.0.0.0"},
        options={"max_chlorine": 20.0},
        entry_id="entry-1",
    )
    hass = types.SimpleNamespace(config_entries=ConfigEntries())
    entity = number.AsekoWaterLevelOffsetNumber(hass, entry)

    asyncio.run(entity.async_set_native_value(20))

    assert calls == [
        ("update", {"max_chlorine": 20.0, "water_level_offset": 20}),
        ("reload", "entry-1"),
    ]
    assert entity.native_value == 20


def test_cloud_forwarding_switch_defaults_enabled(integration_modules):
    switch = integration_modules["switch"]
    entry = types.SimpleNamespace(data={}, options={}, entry_id="entry-1")
    entity = switch.AsekoCloudForwardingSwitch(
        types.SimpleNamespace(options={"forward_enabled": True}),
        types.SimpleNamespace(),
        entry,
    )

    assert entity.is_on is True
    assert entity.icon == "mdi:cloud-sync"


def test_cloud_forwarding_switch_turns_off_preserving_options(integration_modules):
    switch = integration_modules["switch"]
    calls = []

    class ConfigEntries:
        def async_update_entry(self, entry, *, options):
            calls.append(("update", options))
            entry.options = options

    entry = types.SimpleNamespace(
        data={"forward_enabled": True},
        options={"max_chlorine": 20.0, "water_level_offset": 33},
        entry_id="entry-1",
    )
    hass = types.SimpleNamespace(config_entries=ConfigEntries())
    entity = switch.AsekoCloudForwardingSwitch(
        types.SimpleNamespace(options={"forward_enabled": True}), hass, entry
    )

    asyncio.run(entity.async_turn_off())

    assert calls == [
        (
            "update",
            {"max_chlorine": 20.0, "water_level_offset": 33, "forward_enabled": False},
        )
    ]
    assert entity.is_on is False
    assert entity.icon == "mdi:cloud-off-outline"


def test_cloud_forwarding_switch_turns_on_and_listener_reloads(integration_modules):
    switch = integration_modules["switch"]
    calls = []

    class ConfigEntries:
        def __init__(self, hass):
            self.hass = hass

        def async_update_entry(self, entry, *, options):
            calls.append(("update", options))
            entry.options = options
            for listener in entry.update_listeners:
                asyncio.get_running_loop().create_task(listener(self.hass, entry))

        async def async_reload(self, entry_id):
            calls.append(("reload", entry_id))

    async def reload_listener(hass, entry):
        await hass.config_entries.async_reload(entry.entry_id)

    entry = types.SimpleNamespace(
        data={"forward_enabled": False},
        options={"max_chlorine": 20.0, "forward_enabled": False},
        entry_id="entry-1",
        update_listeners=[reload_listener],
    )
    hass = types.SimpleNamespace()
    hass.config_entries = ConfigEntries(hass)
    entity = switch.AsekoCloudForwardingSwitch(
        types.SimpleNamespace(options={"forward_enabled": False}), hass, entry
    )

    async def turn_on_and_run_listener():
        await entity.async_turn_on()
        await asyncio.sleep(0)

    asyncio.run(turn_on_and_run_listener())

    assert calls == [
        ("update", {"max_chlorine": 20.0, "forward_enabled": True}),
        ("reload", "entry-1"),
    ]
    assert entity.is_on is True
    assert entity.icon == "mdi:cloud-sync"


def test_sensor_and_binary_sensor_descriptions_have_mdi_icons(integration_modules):
    for module_name in ("sensor", "binary_sensor"):
        for description in integration_modules[module_name].DESCRIPTIONS:
            assert description.icon
            assert description.icon.startswith("mdi:")


def test_error_binary_sensors_are_problem_class(integration_modules):
    binary_sensor = integration_modules["binary_sensor"]
    for description in binary_sensor.DESCRIPTIONS:
        if description.key.startswith("error_"):
            assert description.device_class == "problem"
            assert description.icon == "mdi:alert-circle-outline"
