import ast
from pathlib import Path

CONFIG_KEYS = {
    "CONF_LISTEN_HOST",
    "CONF_LISTEN_PORT",
    "CONF_FORWARD_ENABLED",
    "CONF_FORWARD_HOST",
    "CONF_FORWARD_PORT",
    "CONF_PROTOCOL_DEBUG",
    "CONF_CAPTURE_ENABLED",
    "CONF_MAX_CHLORINE",
    "CONF_WATER_LEVEL_OFFSET",
}


def test_config_flow_schema_creation_declares_each_key_once():
    tree = ast.parse(
        Path("custom_components/aseko_asin_aqua_home/config_flow.py").read_text()
    )
    required_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "vol"
        and node.func.attr == "Required"
    ]
    keys = [call.args[0].id for call in required_calls]
    assert set(keys) == CONFIG_KEYS
    assert len(keys) == len(CONFIG_KEYS)
    assert all(len(call.args) == 1 for call in required_calls)


def test_default_forwarding_is_one_way_to_aseko_cloud():
    constants = Path("custom_components/aseko_asin_aqua_home/const.py").read_text()
    coordinator = Path(
        "custom_components/aseko_asin_aqua_home/coordinator.py"
    ).read_text()
    assert "DEFAULT_FORWARD_ENABLED = True" in constants
    assert 'DEFAULT_FORWARD_HOST = "pool.aseko.com"' in constants
    assert "DEFAULT_FORWARD_PORT = 47524" in constants
    assert "cloud_writer.write(chunk)" in coordinator
    assert "_discard_cloud_responses(cloud_reader)" in coordinator
    assert "_relay_cloud" not in coordinator


def test_config_flow_schema_can_be_built(monkeypatch):
    import importlib.util
    import sys
    import types

    class Marker:
        def __init__(self, key, *, default=None):
            self.key = key
            self.default = default

    class Schema:
        def __init__(self, mapping):
            self.schema = mapping

    vol = types.ModuleType("voluptuous")
    vol.Required = Marker
    vol.Schema = Schema
    vol.Coerce = lambda target: target
    vol.Range = lambda **kwargs: kwargs
    vol.All = lambda *validators: validators
    monkeypatch.setitem(sys.modules, "voluptuous", vol)

    config_entries = types.ModuleType("homeassistant.config_entries")

    class ConfigFlow:
        def __init_subclass__(cls, **kwargs):
            super().__init_subclass__()

    class OptionsFlow:
        pass

    config_entries.ConfigFlow = ConfigFlow
    config_entries.OptionsFlow = OptionsFlow
    homeassistant = types.ModuleType("homeassistant")
    homeassistant.config_entries = config_entries
    monkeypatch.setitem(sys.modules, "homeassistant", homeassistant)
    monkeypatch.setitem(sys.modules, "homeassistant.config_entries", config_entries)

    package = types.ModuleType("aseko_schema_test")
    package.__path__ = []
    monkeypatch.setitem(sys.modules, package.__name__, package)
    for module_name in ("const", "config_flow"):
        path = Path("custom_components/aseko_asin_aqua_home") / f"{module_name}.py"
        spec = importlib.util.spec_from_file_location(
            f"{package.__name__}.{module_name}", path
        )
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, spec.name, module)
        spec.loader.exec_module(module)
    built = sys.modules[f"{package.__name__}.config_flow"].schema()
    assert {marker.key for marker in built.schema} == {
        "listen_host",
        "listen_port",
        "forward_enabled",
        "forward_host",
        "forward_port",
        "protocol_debug",
        "capture_enabled",
        "max_chlorine",
        "water_level_offset",
    }


def test_config_entry_flow_rates_migrate_from_liters_per_hour_to_ml_min(monkeypatch):
    import asyncio
    import importlib.util
    import sys
    import types

    homeassistant = types.ModuleType("homeassistant")
    config_entries = types.ModuleType("homeassistant.config_entries")
    core = types.ModuleType("homeassistant.core")
    helpers = types.ModuleType("homeassistant.helpers")
    entity_registry = types.ModuleType("homeassistant.helpers.entity_registry")
    entity_registry.async_get = lambda hass: types.SimpleNamespace()
    helpers.entity_registry = entity_registry
    config_entries.ConfigEntry = object
    core.HomeAssistant = object

    package = types.ModuleType("aseko_config_migration_test")
    package.__path__ = [str(Path("custom_components/aseko_asin_aqua_home"))]
    const = types.ModuleType(f"{package.__name__}.const")
    const.CONFIG_ENTRY_VERSION = 2
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
    const.LITERS_PER_HOUR_TO_MILLILITERS_PER_MINUTE = 1000 / 60
    const.PLATFORMS = ["sensor", "binary_sensor", "number", "switch", "button"]
    coordinator = types.ModuleType(f"{package.__name__}.coordinator")
    coordinator.AsekoCoordinator = object
    dosing_tracker = types.ModuleType(f"{package.__name__}.dosing_tracker")
    dosing_tracker.DOSING_CHANNELS = (
        types.SimpleNamespace(key="chlorine"),
        types.SimpleNamespace(key="ph_minus"),
        types.SimpleNamespace(key="flocculation"),
        types.SimpleNamespace(key="algicide"),
    )

    for name, module in {
        "homeassistant": homeassistant,
        "homeassistant.config_entries": config_entries,
        "homeassistant.core": core,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.entity_registry": entity_registry,
        package.__name__: package,
        f"{package.__name__}.const": const,
        f"{package.__name__}.coordinator": coordinator,
        f"{package.__name__}.dosing_tracker": dosing_tracker,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)

    spec = importlib.util.spec_from_file_location(
        package.__name__,
        Path("custom_components/aseko_asin_aqua_home/__init__.py"),
        submodule_search_locations=[str(Path("custom_components/aseko_asin_aqua_home"))],
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, package.__name__, module)
    spec.loader.exec_module(module)

    updates = []

    class ConfigEntries:
        def async_update_entry(self, entry, **kwargs):
            updates.append(kwargs)
            entry.data = kwargs.get("data", entry.data)
            entry.options = kwargs.get("options", entry.options)
            entry.version = kwargs.get("version", entry.version)

    entry = types.SimpleNamespace(
        version=1,
        data={"chlorine_flow_rate": 1.2, "listen_port": 47524},
        options={"ph_minus_flow_rate": 0.6, "water_level_offset": 12},
        entry_id="entry-1",
    )
    hass = types.SimpleNamespace(config_entries=ConfigEntries())

    assert asyncio.run(module.async_migrate_entry(hass, entry)) is True

    assert entry.version == 2
    assert entry.data["chlorine_flow_rate"] == 20.0
    assert entry.options["ph_minus_flow_rate"] == 10.0
    assert entry.data["listen_port"] == 47524
    assert entry.options["water_level_offset"] == 12
    assert updates
