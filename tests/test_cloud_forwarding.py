import asyncio
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys
import types

import pytest

BASE = Path("custom_components/aseko_asin_aqua_home")
PACKAGE = "aseko_cloud_forwarding_test"


class FakeDataUpdateCoordinator:
    def __class_getitem__(cls, item):
        return cls

    def __init__(self, hass, logger, *, name):
        self.hass = hass
        self.logger = logger
        self.name = name
        self.data = None
        self.update_listener_calls = 0

    def async_set_updated_data(self, data):
        self.data = data

    def async_update_listeners(self):
        self.update_listener_calls += 1


class FakeStore:
    def __init__(self, *args):
        self.saved = None

    async def async_load(self):
        return None

    async def async_save(self, data):
        self.saved = data


def install_homeassistant_stubs(monkeypatch):
    homeassistant = types.ModuleType("homeassistant")
    config_entries = types.ModuleType("homeassistant.config_entries")
    core = types.ModuleType("homeassistant.core")
    helpers = types.ModuleType("homeassistant.helpers")
    event = types.ModuleType("homeassistant.helpers.event")
    update_coordinator = types.ModuleType("homeassistant.helpers.update_coordinator")
    storage = types.ModuleType("homeassistant.helpers.storage")

    def callback(func):
        return func

    def async_track_time_interval(*args):
        def cancel():
            return None

        return cancel

    class ConfigEntry:
        pass

    core.HomeAssistant = object
    core.callback = callback
    config_entries.ConfigEntry = ConfigEntry
    event.async_track_time_interval = async_track_time_interval
    update_coordinator.DataUpdateCoordinator = FakeDataUpdateCoordinator
    storage.Store = FakeStore

    for name, module in {
        "homeassistant": homeassistant,
        "homeassistant.config_entries": config_entries,
        "homeassistant.core": core,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.event": event,
        "homeassistant.helpers.update_coordinator": update_coordinator,
        "homeassistant.helpers.storage": storage,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)


@pytest.fixture
def modules(monkeypatch):
    install_homeassistant_stubs(monkeypatch)
    package = types.ModuleType(PACKAGE)
    package.__path__ = [str(BASE)]
    monkeypatch.setitem(sys.modules, PACKAGE, package)

    loaded = {}
    for module_name in (
        "const",
        "dosing_tracker",
        "backwash_tracker",
        "protocol",
        "coordinator",
    ):
        spec = importlib.util.spec_from_file_location(
            f"{PACKAGE}.{module_name}", BASE / f"{module_name}.py"
        )
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, spec.name, module)
        spec.loader.exec_module(module)
        loaded[module_name] = module

    spec = importlib.util.spec_from_file_location(
        PACKAGE,
        BASE / "__init__.py",
        submodule_search_locations=[str(BASE)],
    )
    init_module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, PACKAGE, init_module)
    spec.loader.exec_module(init_module)
    loaded["init"] = init_module
    return loaded


class FakeWriter:
    def __init__(self):
        self.closed = False
        self.wait_closed_called = False
        self.writes = []
        self.drain_calls = 0

    def write(self, chunk):
        self.writes.append(chunk)

    async def drain(self):
        self.drain_calls += 1

    def close(self):
        self.closed = True

    async def wait_closed(self):
        self.wait_closed_called = True

    def get_extra_info(self, name):
        return ("127.0.0.1", 12345) if name == "peername" else None


class FailingDrainWriter(FakeWriter):
    async def drain(self):
        raise ConnectionError("cloud unavailable")


class EmptyReader:
    async def read(self, size):
        return b""


class NeverReader:
    async def read(self, size):
        await asyncio.sleep(60)
        return b""


def coordinator(modules, *, forward_enabled=False):
    return modules["coordinator"].AsekoCoordinator(
        types.SimpleNamespace(),
        "entry-1",
        {
            "listen_host": "0.0.0.0",
            "listen_port": 47524,
            "forward_enabled": forward_enabled,
            "forward_host": "pool.aseko.com",
            "forward_port": 47524,
            "protocol_debug": False,
            "capture_enabled": False,
            "max_chlorine": 20.0,
            "water_level_offset": 33,
            "chlorine_container_size": 20.0,
            "chlorine_flow_rate": 0.0,
            "ph_minus_container_size": 20.0,
            "ph_minus_flow_rate": 0.0,
            "flocculation_container_size": 6.0,
            "flocculation_flow_rate": 0.0,
            "algicide_container_size": 6.0,
            "algicide_flow_rate": 0.0,
        },
    )


async def open_connection_factory(opened):
    opened.append(True)
    return NeverReader(), FakeWriter()


def add_session(coord, module):
    writer = FakeWriter()
    session = module.GatewaySession(gateway_writer=writer)
    coord._sessions[writer] = session
    return session, writer


def test_cloud_forwarding_enabled_without_integration_reload(modules):
    init = modules["init"]
    entry = types.SimpleNamespace(
        data={}, options={"forward_enabled": True}, entry_id="entry-1"
    )
    coord = coordinator(modules, forward_enabled=False)
    reloads = []

    class ConfigEntries:
        async def async_reload(self, entry_id):
            reloads.append(entry_id)

    hass = types.SimpleNamespace(
        data={init.DOMAIN: {entry.entry_id: coord}}, config_entries=ConfigEntries()
    )
    asyncio.run(init._reload(hass, entry))
    assert reloads == []
    assert coord.options["forward_enabled"] is True


def test_cloud_forwarding_disabled_without_integration_reload(modules):
    init = modules["init"]
    entry = types.SimpleNamespace(
        data={}, options={"forward_enabled": False}, entry_id="entry-1"
    )
    coord = coordinator(modules, forward_enabled=True)
    reloads = []

    class ConfigEntries:
        async def async_reload(self, entry_id):
            reloads.append(entry_id)

    hass = types.SimpleNamespace(
        data={init.DOMAIN: {entry.entry_id: coord}}, config_entries=ConfigEntries()
    )
    asyncio.run(init._reload(hass, entry))
    assert reloads == []
    assert coord.options["forward_enabled"] is False


def test_no_double_reload_occurs_when_only_forwarding_changes(modules):
    init = modules["init"]
    entry = types.SimpleNamespace(
        data={}, options={"forward_enabled": False}, entry_id="entry-1"
    )
    coord = coordinator(modules, forward_enabled=True)
    reloads = []

    class ConfigEntries:
        async def async_reload(self, entry_id):
            reloads.append(entry_id)

    hass = types.SimpleNamespace(
        data={init.DOMAIN: {entry.entry_id: coord}}, config_entries=ConfigEntries()
    )
    asyncio.run(init._reload(hass, entry))
    asyncio.run(init._reload(hass, entry))
    assert reloads == []


def test_listener_reloads_when_non_live_option_changes(modules):
    init = modules["init"]
    entry = types.SimpleNamespace(
        data={}, options={"listen_port": 12345}, entry_id="entry-1"
    )
    coord = coordinator(modules, forward_enabled=True)
    reloads = []

    class ConfigEntries:
        async def async_reload(self, entry_id):
            reloads.append(entry_id)

    hass = types.SimpleNamespace(
        data={init.DOMAIN: {entry.entry_id: coord}}, config_entries=ConfigEntries()
    )
    asyncio.run(init._reload(hass, entry))
    assert reloads == ["entry-1"]


def test_local_gateway_writer_remains_open_when_forwarding_is_enabled(
    modules, monkeypatch
):
    module = modules["coordinator"]
    coord = coordinator(modules, forward_enabled=False)
    session, gateway_writer = add_session(coord, module)
    opened = []
    monkeypatch.setattr(
        module.asyncio, "open_connection", lambda *args: open_connection_factory(opened)
    )
    asyncio.run(coord.async_set_forwarding_enabled(True))
    assert opened == [True]
    assert session.cloud_writer is not None
    assert gateway_writer.closed is False


def test_local_gateway_writer_remains_open_when_forwarding_is_disabled(modules):
    module = modules["coordinator"]
    coord = coordinator(modules, forward_enabled=True)
    session, gateway_writer = add_session(coord, module)

    async def run():
        session.cloud_writer = FakeWriter()
        session.cloud_discard_task = asyncio.create_task(asyncio.sleep(60))
        await coord.async_set_forwarding_enabled(False)

    asyncio.run(run())
    assert session.cloud_writer is None
    assert gateway_writer.closed is False


def test_existing_local_sensors_and_last_valid_frame_remain_available_after_toggling(
    modules,
):
    coord = coordinator(modules, forward_enabled=False)
    data = types.SimpleNamespace(relays={})
    coord.async_set_updated_data(data)
    coord.last_valid_frame = datetime.now(timezone.utc)
    asyncio.run(coord.async_set_forwarding_enabled(True))
    asyncio.run(coord.async_set_forwarding_enabled(False))
    assert coord.data is data
    assert coord.last_valid_frame is not None
    assert coord.data_available is True


def test_dosing_tracker_state_is_preserved_after_toggling(modules):
    coord = coordinator(modules, forward_enabled=False)
    coord.dosing_tracker.states["chlorine"].accumulated_runtime_seconds = 123
    asyncio.run(coord.async_set_forwarding_enabled(True))
    asyncio.run(coord.async_set_forwarding_enabled(False))
    assert coord.dosing_tracker.states["chlorine"].accumulated_runtime_seconds == 123


def test_all_unrelated_config_entry_options_remain_unchanged(modules):
    init = modules["init"]
    entry = types.SimpleNamespace(
        data={},
        options={
            "water_level_offset": 12,
            "max_chlorine": 10.5,
            "forward_enabled": False,
        },
        entry_id="entry-1",
    )
    coord = coordinator(modules, forward_enabled=True)
    coord.options["water_level_offset"] = 12
    coord.options["max_chlorine"] = 10.5

    class ConfigEntries:
        async def async_reload(self, entry_id):
            raise AssertionError("reload should not be called")

    hass = types.SimpleNamespace(
        data={init.DOMAIN: {entry.entry_id: coord}}, config_entries=ConfigEntries()
    )
    asyncio.run(init._reload(hass, entry))
    assert entry.options == {
        "water_level_offset": 12,
        "max_chlorine": 10.5,
        "forward_enabled": False,
    }


def test_cloud_connection_failure_does_not_interrupt_local_sensor_updates(
    modules, monkeypatch
):
    module = modules["coordinator"]
    coord = coordinator(modules, forward_enabled=False)
    _, gateway_writer = add_session(coord, module)
    coord.async_set_updated_data(types.SimpleNamespace(relays={}))
    coord.last_valid_frame = datetime.now(timezone.utc)

    async def fail_open(*args):
        raise OSError("refused")

    monkeypatch.setattr(module.asyncio, "open_connection", fail_open)
    asyncio.run(coord.async_set_forwarding_enabled(True))
    assert gateway_writer.closed is False
    assert coord.data_available is True


def test_new_gateway_session_opens_cloud_forwarding_when_enabled(modules, monkeypatch):
    module = modules["coordinator"]
    coord = coordinator(modules, forward_enabled=True)
    opened = []
    monkeypatch.setattr(
        module.asyncio, "open_connection", lambda *args: open_connection_factory(opened)
    )
    asyncio.run(coord._handle_client(EmptyReader(), FakeWriter()))
    assert opened == [True]


def test_new_gateway_session_does_not_open_cloud_forwarding_when_disabled(
    modules, monkeypatch
):
    module = modules["coordinator"]
    coord = coordinator(modules, forward_enabled=False)
    opened = []
    monkeypatch.setattr(
        module.asyncio, "open_connection", lambda *args: open_connection_factory(opened)
    )
    asyncio.run(coord._handle_client(EmptyReader(), FakeWriter()))
    assert opened == []


def test_cloud_writer_closes_cleanly_when_forwarding_is_disabled(modules):
    module = modules["coordinator"]
    coord = coordinator(modules, forward_enabled=True)
    session, _ = add_session(coord, module)
    cloud_writer = FakeWriter()
    session.cloud_writer = cloud_writer
    asyncio.run(coord.async_set_forwarding_enabled(False))
    assert cloud_writer.closed is True
    assert cloud_writer.wait_closed_called is True
    assert session.cloud_writer is None


def test_cloud_response_discard_task_is_cancelled_cleanly(modules):
    module = modules["coordinator"]
    coord = coordinator(modules, forward_enabled=True)
    session, _ = add_session(coord, module)

    async def sleep_forever():
        await asyncio.sleep(60)

    async def run():
        session.cloud_discard_task = asyncio.create_task(sleep_forever())
        await coord.async_set_forwarding_enabled(False)
        assert session.cloud_discard_task is None

    asyncio.run(run())


def test_cloud_write_failure_keeps_local_gateway_open(modules):
    module = modules["coordinator"]
    coord = coordinator(modules, forward_enabled=True)
    session, gateway_writer = add_session(coord, module)
    cloud_writer = FailingDrainWriter()
    session.cloud_writer = cloud_writer
    asyncio.run(coord._forward_chunk_to_cloud(session, b"abc"))
    assert cloud_writer.closed is True
    assert gateway_writer.closed is False
    assert session.cloud_writer is None


class HangingCloseWriter(FakeWriter):
    async def wait_closed(self):
        self.wait_closed_called = True
        await asyncio.sleep(60)


class FakeServer:
    def __init__(self):
        self.closed = False
        self.wait_closed_called = False

    def close(self):
        self.closed = True

    async def wait_closed(self):
        self.wait_closed_called = True


class FakeConfigEntriesForUnload:
    def __init__(self):
        self.unloaded_entries = []

    async def async_unload_platforms(self, entry, platforms):
        self.unloaded_entries.append((entry.entry_id, tuple(platforms)))
        return True


def unload_hass(init, coord, entry_id="entry-1"):
    return types.SimpleNamespace(
        data={init.DOMAIN: {entry_id: coord}},
        config_entries=FakeConfigEntriesForUnload(),
    )


def test_config_entry_unload_completes_when_no_clients_are_connected(modules):
    init = modules["init"]
    coord = coordinator(modules)
    server = FakeServer()
    coord.server = server
    entry = types.SimpleNamespace(entry_id="entry-1")
    hass = unload_hass(init, coord)

    assert asyncio.run(init.async_unload_entry(hass, entry)) is True
    assert server.closed is True
    assert server.wait_closed_called is True
    assert hass.data[init.DOMAIN] == {}


def test_config_entry_unload_completes_with_active_gateway_session(
    modules, monkeypatch
):
    init = modules["init"]
    module = modules["coordinator"]
    monkeypatch.setattr(module, "_CLOSE_TIMEOUT", 0.01)
    coord = coordinator(modules)
    entry = types.SimpleNamespace(entry_id="entry-1")
    hass = unload_hass(init, coord)
    gateway_writer = FakeWriter()

    async def run():
        task = asyncio.create_task(coord._handle_client(NeverReader(), gateway_writer))
        await asyncio.sleep(0)
        assert coord._sessions
        unloaded = await init.async_unload_entry(hass, entry)
        assert unloaded is True
        assert task.done()

    asyncio.run(run())
    assert gateway_writer.closed is True
    assert gateway_writer.wait_closed_called is True
    assert coord._sessions == {}
    assert coord.clients == 0


def test_config_entry_unload_completes_with_active_cloud_writer(modules):
    init = modules["init"]
    module = modules["coordinator"]
    coord = coordinator(modules)
    session, _ = add_session(coord, module)
    cloud_writer = FakeWriter()
    session.cloud_writer = cloud_writer
    entry = types.SimpleNamespace(entry_id="entry-1")
    hass = unload_hass(init, coord)

    assert asyncio.run(init.async_unload_entry(hass, entry)) is True
    assert cloud_writer.closed is True
    assert cloud_writer.wait_closed_called is True
    assert session.cloud_writer is None


def test_config_entry_unload_completes_when_cloud_writer_wait_closed_hangs(
    modules, monkeypatch
):
    init = modules["init"]
    module = modules["coordinator"]
    monkeypatch.setattr(module, "_CLOSE_TIMEOUT", 0.01)
    coord = coordinator(modules)
    session, _ = add_session(coord, module)
    cloud_writer = HangingCloseWriter()
    session.cloud_writer = cloud_writer
    entry = types.SimpleNamespace(entry_id="entry-1")
    hass = unload_hass(init, coord)

    assert asyncio.run(init.async_unload_entry(hass, entry)) is True
    assert cloud_writer.closed is True
    assert cloud_writer.wait_closed_called is True
    assert coord._sessions == {}


def test_config_entry_unload_completes_when_gateway_writer_wait_closed_hangs(
    modules, monkeypatch
):
    init = modules["init"]
    module = modules["coordinator"]
    monkeypatch.setattr(module, "_CLOSE_TIMEOUT", 0.01)
    coord = coordinator(modules)
    session, gateway_writer = add_session(coord, module)
    hanging_gateway_writer = HangingCloseWriter()
    session.gateway_writer = hanging_gateway_writer
    coord._sessions = {hanging_gateway_writer: session}
    entry = types.SimpleNamespace(entry_id="entry-1")
    hass = unload_hass(init, coord)

    assert asyncio.run(init.async_unload_entry(hass, entry)) is True
    assert hanging_gateway_writer.closed is True
    assert hanging_gateway_writer.wait_closed_called is True
    assert coord._sessions == {}


def test_active_sessions_are_cleared_after_unload(modules):
    init = modules["init"]
    module = modules["coordinator"]
    coord = coordinator(modules)
    add_session(coord, module)
    add_session(coord, module)
    entry = types.SimpleNamespace(entry_id="entry-1")
    hass = unload_hass(init, coord)

    assert asyncio.run(init.async_unload_entry(hass, entry)) is True
    assert coord._sessions == {}
    assert coord.clients == 0


def test_persistent_dosing_state_is_saved_before_unload_completes(modules):
    init = modules["init"]
    coord = coordinator(modules)
    coord.dosing_tracker.states["chlorine"].accumulated_runtime_seconds = 321
    entry = types.SimpleNamespace(entry_id="entry-1")
    hass = unload_hass(init, coord)

    assert asyncio.run(init.async_unload_entry(hass, entry)) is True
    assert (
        coord.dosing_tracker._store.saved["channels"]["chlorine"][
            "accumulated_runtime_seconds"
        ]
        == 321
    )


def test_persistent_backwash_state_is_saved_before_unload_completes(modules):
    init = modules["init"]
    coord = coordinator(modules)
    coord.backwash_tracker.state.last_backwash_timestamp = "2026-06-03T10:00:00+00:00"
    coord.backwash_tracker._dirty = True
    entry = types.SimpleNamespace(entry_id="entry-1")
    hass = unload_hass(init, coord)

    assert asyncio.run(init.async_unload_entry(hass, entry)) is True
    assert (
        coord.backwash_tracker._store.saved["state"]["last_backwash_timestamp"]
        == "2026-06-03T10:00:00+00:00"
    )
