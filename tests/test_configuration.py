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
