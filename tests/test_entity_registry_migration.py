import asyncio
import importlib.util
from pathlib import Path
import sys
import types

BASE = Path("custom_components/aseko_asin_aqua_home")
PACKAGE = "aseko_registry_migration_test"


class RegistryEntry:
    def __init__(
        self,
        entity_id,
        unique_id,
        *,
        config_entry_id="entry-1",
        platform="aseko_asin_aqua_home",
    ):
        self.entity_id = entity_id
        self.unique_id = unique_id
        self.config_entry_id = config_entry_id
        self.platform = platform


class Registry:
    def __init__(self, entries):
        self.entries = entries
        self.updates = []

    def async_get(self, entity_id):
        return self.entries.get(entity_id)

    def async_update_entity(self, entity_id, **kwargs):
        self.updates.append((entity_id, kwargs))
        entry = self.entries.pop(entity_id)
        new_entity_id = kwargs["new_entity_id"]
        entry.entity_id = new_entity_id
        self.entries[new_entity_id] = entry


def load_init_module(monkeypatch, registry):
    homeassistant = types.ModuleType("homeassistant")
    config_entries = types.ModuleType("homeassistant.config_entries")
    core = types.ModuleType("homeassistant.core")
    ha_const = types.ModuleType("homeassistant.const")
    ha_const.EVENT_HOMEASSISTANT_STOP = "homeassistant_stop"
    helpers = types.ModuleType("homeassistant.helpers")
    entity_registry = types.ModuleType("homeassistant.helpers.entity_registry")
    entity_registry.async_get = lambda hass: registry
    helpers.entity_registry = entity_registry
    config_entries.ConfigEntry = object
    core.HomeAssistant = object

    package = types.ModuleType(PACKAGE)
    package.__path__ = [str(BASE)]
    const = types.ModuleType(f"{PACKAGE}.const")
    const.CONF_FORWARD_ENABLED = "forward_enabled"
    const.CONF_TIME_CORRECTION_THRESHOLD_MINUTES = "time_correction_threshold_minutes"
    const.CONF_WATER_LEVEL_ERROR_LABELS = "water_level_error_labels"
    const.CONF_WATER_LEVEL_OFFSET = "water_level_offset"
    const.DEFAULT_CAPTURE_ENABLED = False
    const.DEFAULT_FORWARD_ENABLED = True
    const.DEFAULT_FORWARD_HOST = "pool.aseko.com"
    const.DEFAULT_FORWARD_PORT = 47524
    const.DEFAULT_LISTEN_HOST = "0.0.0.0"
    const.DEFAULT_LISTEN_PORT = 47524
    const.DEFAULT_MAX_CHLORINE = 20.0
    const.DEFAULT_PROTOCOL_DEBUG = False
    const.DEFAULT_TIME_CORRECTION_THRESHOLD_MINUTES = 5
    const.DEFAULT_WATER_LEVEL_ERROR_LABELS = False
    const.DEFAULT_WATER_LEVEL_OFFSET = 33
    const.DEVICE_IDENTIFIER = "asin_aqua_home"
    const.DOMAIN = "aseko_asin_aqua_home"
    const.PLATFORMS = ["sensor", "binary_sensor", "number", "switch", "button"]
    coordinator = types.ModuleType(f"{PACKAGE}.coordinator")
    coordinator.AsekoCoordinator = object
    dosing_tracker = types.ModuleType(f"{PACKAGE}.dosing_tracker")
    dosing_tracker.DOSING_CHANNELS = ()

    for name, module in {
        "homeassistant": homeassistant,
        "homeassistant.const": ha_const,
        "homeassistant.config_entries": config_entries,
        "homeassistant.core": core,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.entity_registry": entity_registry,
        PACKAGE: package,
        f"{PACKAGE}.const": const,
        f"{PACKAGE}.coordinator": coordinator,
        f"{PACKAGE}.dosing_tracker": dosing_tracker,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)

    spec = importlib.util.spec_from_file_location(
        PACKAGE,
        BASE / "__init__.py",
        submodule_search_locations=[str(BASE)],
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, PACKAGE, module)
    spec.loader.exec_module(module)
    return module


def test_setup_preserves_all_existing_entity_ids(monkeypatch):
    from unittest.mock import AsyncMock, Mock

    ids = (
        "sensor.asin_aqua_home_asin_aqua_home_last_backwash",
        "sensor.asin_aqua_home_last_backwash",
        "sensor.asin_aqua_home_3",
        "sensor.my_custom_pool_sensor",
    )
    registry = Registry({key: RegistryEntry(key, "asin_aqua_home_last_backwash") for key in ids})
    module = load_init_module(monkeypatch, registry)
    coordinator = types.SimpleNamespace(async_start=AsyncMock(), async_stop=AsyncMock())
    module.AsekoCoordinator = lambda *args: coordinator
    entry = types.SimpleNamespace(entry_id="entry-1", data={}, options={},
                                  async_on_unload=lambda listener: None,
                                  add_update_listener=lambda listener: None)
    register_stop = Mock()
    hass = types.SimpleNamespace(data={}, bus=types.SimpleNamespace(async_listen_once=register_stop), config_entries=types.SimpleNamespace(
        async_forward_entry_setups=AsyncMock()))
    assert asyncio.run(module.async_setup_entry(hass, entry)) is True
    assert registry.updates == []
    assert tuple(registry.entries) == ids
    assert all(key == value.entity_id for key, value in registry.entries.items())
    register_stop.assert_called_once_with("homeassistant_stop", coordinator.async_stop)
