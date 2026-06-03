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
    const.CONF_WATER_LEVEL_OFFSET = "water_level_offset"
    const.DEFAULT_CAPTURE_ENABLED = False
    const.DEFAULT_FORWARD_ENABLED = True
    const.DEFAULT_FORWARD_HOST = "pool.aseko.com"
    const.DEFAULT_FORWARD_PORT = 47524
    const.DEFAULT_LISTEN_HOST = "0.0.0.0"
    const.DEFAULT_LISTEN_PORT = 47524
    const.DEFAULT_MAX_CHLORINE = 20.0
    const.DEFAULT_PROTOCOL_DEBUG = False
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
    module._known_semantic_entity_keys = lambda: (
        ("sensor", "last_backwash"),
        ("sensor", "chlorine_target"),
    )
    return module


def test_duplicated_prefix_registry_migration_renames_only_known_generated_ids(monkeypatch):
    entries = {
        "sensor.asin_aqua_home_asin_aqua_home_last_backwash": RegistryEntry(
            "sensor.asin_aqua_home_asin_aqua_home_last_backwash",
            "asin_aqua_home_last_backwash",
        ),
        "sensor.asin_aqua_home_asin_aqua_home_chlorine_target": RegistryEntry(
            "sensor.asin_aqua_home_asin_aqua_home_chlorine_target",
            "custom_unique_id",
        ),
        "sensor.user_customized_duplicate_name": RegistryEntry(
            "sensor.user_customized_duplicate_name",
            "asin_aqua_home_last_backwash",
        ),
    }
    registry = Registry(entries)
    module = load_init_module(monkeypatch, registry)

    asyncio.run(
        module._async_migrate_duplicated_prefix_entity_ids(
            types.SimpleNamespace(), types.SimpleNamespace(entry_id="entry-1")
        )
    )

    assert registry.updates == [
        (
            "sensor.asin_aqua_home_asin_aqua_home_last_backwash",
            {"new_entity_id": "sensor.asin_aqua_home_last_backwash"},
        )
    ]
    assert "sensor.asin_aqua_home_last_backwash" in registry.entries
    assert (
        registry.entries["sensor.asin_aqua_home_last_backwash"].unique_id
        == "asin_aqua_home_last_backwash"
    )
    assert "sensor.asin_aqua_home_asin_aqua_home_chlorine_target" in registry.entries
    assert "sensor.user_customized_duplicate_name" in registry.entries


def test_duplicated_prefix_registry_migration_skips_existing_target(monkeypatch, caplog):
    entries = {
        "sensor.asin_aqua_home_asin_aqua_home_last_backwash": RegistryEntry(
            "sensor.asin_aqua_home_asin_aqua_home_last_backwash",
            "asin_aqua_home_last_backwash",
        ),
        "sensor.asin_aqua_home_last_backwash": RegistryEntry(
            "sensor.asin_aqua_home_last_backwash",
            "asin_aqua_home_last_backwash_2",
        ),
    }
    registry = Registry(entries)
    module = load_init_module(monkeypatch, registry)

    asyncio.run(
        module._async_migrate_duplicated_prefix_entity_ids(
            types.SimpleNamespace(), types.SimpleNamespace(entry_id="entry-1")
        )
    )

    assert registry.updates == []
    assert "target entity ID already exists" in caplog.text
