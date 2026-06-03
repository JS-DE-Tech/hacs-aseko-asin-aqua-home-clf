import importlib.util
from pathlib import Path
import sys
import types
from dataclasses import dataclass

import asyncio
import re
import subprocess

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
    button = types.ModuleType("homeassistant.components.button")
    const = types.ModuleType("homeassistant.const")
    helpers = types.ModuleType("homeassistant.helpers")
    update_coordinator = types.ModuleType("homeassistant.helpers.update_coordinator")
    entity = types.ModuleType("homeassistant.helpers.entity")
    storage = types.ModuleType("homeassistant.helpers.storage")
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
        native_step: float | None = None
        mode: str | None = None
        entity_category: str | None = None

    class SensorDeviceClass:
        TEMPERATURE = "temperature"
        DURATION = "duration"
        TIMESTAMP = "timestamp"

    class BinarySensorDeviceClass:
        PROBLEM = "problem"

    class NumberMode:
        BOX = "box"

    class EntityCategory:
        CONFIG = "config"

    class Entity:
        def async_write_ha_state(self):
            self._ha_state_written = True

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
    switch.SwitchEntityDescription = EntityDescription
    button.ButtonEntity = Entity
    button.ButtonEntityDescription = EntityDescription
    const.UnitOfTemperature = types.SimpleNamespace(CELSIUS="°C")
    const.CONCENTRATION_PARTS_PER_MILLION = "ppm"
    entity.EntityCategory = EntityCategory
    update_coordinator.CoordinatorEntity = CoordinatorEntity

    class Store:
        def __init__(self, *args):
            self.saved = None
        async def async_load(self):
            return None
        async def async_save(self, data):
            self.saved = data

    storage.Store = Store
    config_entries.ConfigEntry = object
    core.HomeAssistant = object

    modules = {
        "homeassistant": homeassistant,
        "homeassistant.components": components,
        "homeassistant.components.sensor": sensor,
        "homeassistant.components.binary_sensor": binary_sensor,
        "homeassistant.components.number": number,
        "homeassistant.components.switch": switch,
        "homeassistant.components.button": button,
        "homeassistant.const": const,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.update_coordinator": update_coordinator,
        "homeassistant.helpers.entity": entity,
        "homeassistant.helpers.storage": storage,
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
    for module_name in ("const", "dosing_tracker", "backwash_tracker", "protocol", "sensor", "binary_sensor", "number", "switch", "button"):
        spec = importlib.util.spec_from_file_location(
            f"{PACKAGE}.{module_name}", BASE / f"{module_name}.py"
        )
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, spec.name, module)
        spec.loader.exec_module(module)
        loaded[module_name] = module
    return loaded


def test_platforms_included(integration_modules):
    assert integration_modules["const"].PLATFORMS == [
        "sensor",
        "binary_sensor",
        "number",
        "switch",
        "button",
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

    assert calls == [("update", {"max_chlorine": 20.0, "water_level_offset": 20})]
    assert entity._ha_state_written is True
    assert entity.native_value == 20


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


def test_dosing_number_descriptions_have_defaults_and_unique_ids(integration_modules):
    number = integration_modules["number"]
    defaults = {description.key: description.default_value for description in number.DOSING_NUMBER_DESCRIPTIONS}
    assert defaults["chlorine_container_size"] == 20.0
    assert defaults["ph_minus_container_size"] == 20.0
    assert defaults["flocculation_container_size"] == 6.0
    assert defaults["algicide_container_size"] == 6.0
    assert defaults["chlorine_flow_rate"] == 0.0
    entry = types.SimpleNamespace(data={}, options={}, entry_id="entry-1")
    hass = types.SimpleNamespace()
    entity = number.AsekoConfigNumber(hass, entry, number.DOSING_NUMBER_DESCRIPTIONS[0])
    assert entity._attr_unique_id == "asin_aqua_home_chlorine_container_size"
    assert entity._attr_has_entity_name is True


def test_cloud_forwarding_switch_updates_option_and_icons(integration_modules):
    switch = integration_modules["switch"]
    calls = []

    class ConfigEntries:
        def async_update_entry(self, entry, *, options):
            calls.append(("update", options))
            entry.options = options

        async def async_reload(self, entry_id):
            calls.append(("reload", entry_id))

    class Coordinator:
        def __init__(self):
            self.forwarding_updates = []

        async def async_set_forwarding_enabled(self, enabled):
            self.forwarding_updates.append(enabled)

    entry = types.SimpleNamespace(data={}, options={"water_level_offset": 33}, entry_id="entry-1")
    coordinator = Coordinator()
    hass = types.SimpleNamespace(
        config_entries=ConfigEntries(),
        data={switch.DOMAIN: {entry.entry_id: coordinator}},
    )
    entity = switch.AsekoCloudForwardingSwitch(hass, entry)
    assert entity._attr_unique_id == "asin_aqua_home_cloud_forwarding"
    assert entity.suggested_object_id == "asin_aqua_home_cloud_forwarding"
    assert entity._attr_has_entity_name is True
    assert entity.is_on is True
    assert entity.icon == "mdi:cloud-sync"
    asyncio.run(entity.async_turn_off())
    assert coordinator.forwarding_updates == [False]
    assert entry.options == {"water_level_offset": 33, "forward_enabled": False}
    assert entity.icon == "mdi:cloud-off-outline"
    assert entity._ha_state_written is True
    asyncio.run(entity.async_turn_on())
    assert coordinator.forwarding_updates == [False, True]
    assert entry.options == {"water_level_offset": 33, "forward_enabled": True}
    assert calls == [
        ("update", {"water_level_offset": 33, "forward_enabled": False}),
        ("update", {"water_level_offset": 33, "forward_enabled": True}),
    ]


def test_button_descriptions_have_stable_unique_ids(integration_modules):
    button = integration_modules["button"]
    coordinator = types.SimpleNamespace()
    entity = button.AsekoContainerReplacedButton(coordinator, button.BUTTON_DESCRIPTIONS[0])
    assert entity._attr_unique_id == "asin_aqua_home_chlorine_container_replaced"
    assert entity.suggested_object_id == "asin_aqua_home_chlorine_container_replaced"
    assert entity._attr_has_entity_name is True
    assert all(description.icon == "mdi:refresh" for description in button.BUTTON_DESCRIPTIONS)


def test_dosing_sensor_descriptions_are_present(integration_modules):
    sensor = integration_modules["sensor"]
    keys = {description.key for description in sensor.DESCRIPTIONS}
    assert "chlorine_runtime_since_replacement" in keys
    assert "ph_minus_remaining_percent" in keys
    assert "flocculation_suggested_flow_rate" in keys
    assert "algicide_last_container_replacement" in keys


def test_dosing_sensor_calculations_and_availability(integration_modules):
    sensor = integration_modules["sensor"]
    state = types.SimpleNamespace(
        accumulated_runtime_seconds=3600,
        last_container_replacement_timestamp="2026-01-01T00:00:00+00:00",
    )
    tracker = types.SimpleNamespace(states={"chlorine": state})
    coordinator = types.SimpleNamespace(
        dosing_tracker=tracker,
        options={"chlorine_container_size": 20.0, "chlorine_flow_rate": 2.0},
        data=None,
        data_available=True,
    )
    descriptions = {description.key: description for description in sensor.DESCRIPTIONS}
    consumed = sensor.AsekoSensor(coordinator, descriptions["chlorine_consumed_liters"])
    remaining = sensor.AsekoSensor(coordinator, descriptions["chlorine_remaining_liters"])
    percent = sensor.AsekoSensor(coordinator, descriptions["chlorine_remaining_percent"])
    suggested = sensor.AsekoSensor(coordinator, descriptions["chlorine_suggested_flow_rate"])
    runtime = sensor.AsekoSensor(coordinator, descriptions["chlorine_runtime_since_replacement"])
    assert runtime.native_value == 3600
    assert consumed.native_value == 2.0
    assert remaining.native_value == 18.0
    assert percent.native_value == 90.0
    assert suggested.native_value == 20.0

    coordinator.options["chlorine_flow_rate"] = 0.0
    assert consumed.available is False
    assert remaining.available is False
    assert percent.available is False
    assert suggested.available is True
    state.accumulated_runtime_seconds = 0
    assert suggested.available is False


def test_remaining_volume_is_clamped(integration_modules):
    sensor = integration_modules["sensor"]
    state = types.SimpleNamespace(
        accumulated_runtime_seconds=20 * 3600,
        last_container_replacement_timestamp=None,
    )
    coordinator = types.SimpleNamespace(
        dosing_tracker=types.SimpleNamespace(states={"chlorine": state}),
        options={"chlorine_container_size": 20.0, "chlorine_flow_rate": 2.0},
        data=None,
        data_available=True,
    )
    descriptions = {description.key: description for description in sensor.DESCRIPTIONS}
    remaining = sensor.AsekoSensor(coordinator, descriptions["chlorine_remaining_liters"])
    percent = sensor.AsekoSensor(coordinator, descriptions["chlorine_remaining_percent"])
    assert remaining.native_value == 0
    assert percent.native_value == 0


def test_entities_use_supported_semantic_suggested_object_ids(integration_modules):
    unsupported_attr = "_attr_" + "suggested_object_id"
    entity_id_assignment = re.compile(r"\bentity_id\s*=")
    entity_files = [
        BASE / "sensor.py",
        BASE / "binary_sensor.py",
        BASE / "number.py",
        BASE / "switch.py",
        BASE / "button.py",
    ]
    for path in entity_files:
        source = path.read_text()
        assert unsupported_attr not in source
        assert not entity_id_assignment.search(source)

    sensor = integration_modules["sensor"]
    binary_sensor = integration_modules["binary_sensor"]
    number = integration_modules["number"]
    switch = integration_modules["switch"]
    button = integration_modules["button"]

    coordinator = types.SimpleNamespace(data=None, data_available=True)
    entry = types.SimpleNamespace(data={}, options={}, entry_id="entry-1")
    hass = types.SimpleNamespace()

    entities = [
        *(sensor.AsekoSensor(coordinator, description) for description in sensor.DESCRIPTIONS),
        *(
            binary_sensor.AsekoBinarySensor(coordinator, description)
            for description in binary_sensor.DESCRIPTIONS
        ),
        number.AsekoWaterLevelOffsetNumber(hass, entry),
        *(
            number.AsekoConfigNumber(hass, entry, description)
            for description in number.DOSING_NUMBER_DESCRIPTIONS
        ),
        switch.AsekoCloudForwardingSwitch(hass, entry),
        *(
            button.AsekoContainerReplacedButton(coordinator, description)
            for description in button.BUTTON_DESCRIPTIONS
        ),
    ]

    semantic_ids = {entity.suggested_object_id for entity in entities}
    assert all(hasattr(type(entity), "suggested_object_id") for entity in entities)
    assert all(value.startswith("asin_aqua_home_") for value in semantic_ids)
    assert all(re.fullmatch(r"[a-z0-9_]+", value) for value in semantic_ids)
    assert not any(re.search(r"_\d+$", value) for value in semantic_ids)
    assert len(semantic_ids) == len(entities)

    expected_suggestions = {
        "asin_aqua_home_air_temperature",
        "asin_aqua_home_chlorine",
        "asin_aqua_home_last_backwash",
        "asin_aqua_home_error_no_probe_flow",
        "asin_aqua_home_relay_backwash",
        "asin_aqua_home_relay_filling",
        "asin_aqua_home_relay_chlorine",
        "asin_aqua_home_cloud_forwarding",
        "asin_aqua_home_water_level_offset",
        "asin_aqua_home_chlorine_container_replaced",
    }
    assert expected_suggestions <= semantic_ids

    unique_ids = {entity._attr_unique_id for entity in entities}
    assert "asin_aqua_home_air_temperature" in unique_ids
    assert "asin_aqua_home_chlorine" in unique_ids
    assert "asin_aqua_home_last_backwash" in unique_ids
    assert "asin_aqua_home_error_no_probe_flow" in unique_ids
    assert "asin_aqua_home_relay_backwash" in unique_ids
    assert "asin_aqua_home_relay_filling" in unique_ids
    assert "asin_aqua_home_relay_chlorine" in unique_ids
    assert "asin_aqua_home_cloud_forwarding" in unique_ids
    assert "asin_aqua_home_water_level_offset" in unique_ids
    assert "asin_aqua_home_chlorine_container_replaced" in unique_ids


def test_chemistry_and_relay_icons_are_consistent(integration_modules):
    sensor = integration_modules["sensor"]
    binary_sensor = integration_modules["binary_sensor"]
    sensor_icons = {description.key: description.icon for description in sensor.DESCRIPTIONS}
    binary_icons = {
        description.key: description.icon for description in binary_sensor.DESCRIPTIONS
    }

    assert sensor_icons["chlorine"] == "mdi:flask-round-bottom"
    assert sensor_icons["chlorine_target"] == "mdi:flask-round-bottom"
    assert binary_icons["relay_chlorine"] == "mdi:flask-round-bottom"

    assert sensor_icons["ph"] == "mdi:flask-outline"
    assert sensor_icons["ph_target"] == "mdi:flask-outline"
    assert binary_icons["relay_ph_minus"] == "mdi:flask-outline"

    assert sensor_icons["flocculation_dose"] == "mdi:bottle-tonic-outline"
    assert binary_icons["relay_flocculation"] == "mdi:bottle-tonic-outline"

    assert sensor_icons["algicide_dose"] == "mdi:bottle-tonic"
    assert binary_icons["relay_algicide"] == "mdi:bottle-tonic"

    assert binary_icons["relay_backwash"] == "mdi:wave-arrow-down"
    assert binary_icons["relay_filling"] == "mdi:waves-arrow-up"
    assert sensor_icons["last_backwash"] == "mdi:recycle"

    for description in binary_sensor.DESCRIPTIONS:
        if description.key.startswith("error_"):
            assert description.device_class == "problem"
            assert description.icon == "mdi:alert-circle-outline"


def test_no_image_files_or_frontend_resources_added():
    added_files = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=A", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    image_suffixes = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
    frontend_suffixes = {".js", ".mjs", ".ts", ".tsx", ".css"}

    assert not any(Path(path).suffix.lower() in image_suffixes for path in added_files)
    assert not any(Path(path).suffix.lower() in frontend_suffixes for path in added_files)


def test_protocol_behavior_files_are_unchanged_in_this_patch():
    changed_files = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    restricted_behavior_files = {
        "custom_components/aseko_asin_aqua_home/protocol.py",
        "custom_components/aseko_asin_aqua_home/coordinator.py",
        "custom_components/aseko_asin_aqua_home/backwash_tracker.py",
        "custom_components/aseko_asin_aqua_home/dosing_tracker.py",
        "custom_components/aseko_asin_aqua_home/config_flow.py",
        "custom_components/aseko_asin_aqua_home/__init__.py",
        "custom_components/aseko_asin_aqua_home/strings.json",
    }

    assert not restricted_behavior_files.intersection(changed_files)
