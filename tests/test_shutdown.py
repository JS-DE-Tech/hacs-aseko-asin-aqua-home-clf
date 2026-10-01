"""Shutdown regressions: real loopback sockets, HA storage/scheduler stubs only."""

import asyncio
from contextlib import asynccontextmanager
import types
from unittest.mock import AsyncMock

import pytest

from test_cloud_forwarding import coordinator, modules, unload_hass  # noqa: F401

FRAME = bytes.fromhex(
    "069132d702011a0914152d00000002cd00130013001f9a008700b96eaa00ffff00000000005b030c"
    "069132d702031a0914152d004804001c09000f001600170002cc00c0050c00060028025803840144"
    "069132d702021a0914152d000026003c003c003c00016c6d6e6f012c0d02580f0f0f1e14ffc402ba"
)


async def until(predicate):
    async with asyncio.timeout(2):
        while not predicate():
            await asyncio.sleep(0.001)


async def no_background_tasks():
    await asyncio.sleep(0)
    assert asyncio.all_tasks() == {asyncio.current_task()}


@asynccontextmanager
async def running(modules, *, cloud=False):
    coord = coordinator(modules, forward_enabled=cloud)
    coord.options.update(listen_host="127.0.0.1", listen_port=0)
    cloud_peers = []
    cloud_server = None
    clients = []
    if cloud:
        cloud_server = await asyncio.start_server(
            lambda r, w: cloud_peers.append((r, w)), "127.0.0.1", 0
        )
        coord.options.update(
            forward_host="127.0.0.1",
            forward_port=cloud_server.sockets[0].getsockname()[1],
        )
    await coord.async_start()
    port = coord.server.sockets[0].getsockname()[1]

    async def connect():
        pair = await asyncio.open_connection("127.0.0.1", port)
        clients.append(pair)
        await until(lambda: coord.clients == len(clients))
        return pair

    try:
        yield coord, connect, cloud_peers
    finally:
        # Also release sockets if an assertion fails against the unfixed version.
        for _, writer in clients + cloud_peers:
            writer.transport.abort()
        if coord.server is not None:
            coord.server.close()
        for session in list(coord._sessions.values()):
            session.gateway_writer.transport.abort()
            if session.cloud_writer:
                session.cloud_writer.transport.abort()
        if cloud_server is not None:
            cloud_server.close()
            await asyncio.wait_for(cloud_server.wait_closed(), 2)
        await asyncio.wait_for(coord.async_stop(), 2)


@pytest.mark.parametrize("clients", [0, 1, 4])
def test_stop_real_tcp_clients(modules, clients):
    async def run():
        async with running(modules) as (coord, connect, _):
            peers = [await connect() for _ in range(clients)]
            sessions = list(coord._sessions.values())
            server = coord.server
            await asyncio.wait_for(coord.async_stop(), 2)
            assert not server.is_serving()
            assert coord.server is None
            assert coord.clients == 0
            assert not coord._sessions
            assert all(s.session_task.done() for s in sessions)
            for reader, _ in peers:
                assert await asyncio.wait_for(reader.read(), 1) == b""
        await no_background_tasks()
    asyncio.run(run())


def test_stop_real_cloud_preserves_local_decoding_and_storage(modules):
    async def run():
        async with running(modules, cloud=True) as (coord, connect, cloud):
            reader, writer = await connect()
            await until(lambda: cloud and next(iter(coord._sessions.values())).cloud_writer)
            session = next(iter(coord._sessions.values()))
            cloud_task = session.cloud_discard_task
            writer.write(FRAME)
            await writer.drain()
            assert await asyncio.wait_for(cloud[0][0].readexactly(len(FRAME)), 1) == FRAME
            await until(lambda: coord.data is not None)
            assert coord.data.sensors["chlorine"] == 0.19
            # Cloud responses must not reach the controller.
            cloud[0][1].write(b"cloud response")
            await cloud[0][1].drain()
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(reader.read(1), 0.02)
            coord.dosing_tracker.states["chlorine"].accumulated_runtime_seconds = 321
            coord.backwash_tracker.state.last_backwash_timestamp = "2026-09-01T12:00:00+00:00"
            coord.backwash_tracker._dirty = True
            coord.forecast._dirty = True
            await asyncio.wait_for(coord.async_stop(), 2)
            assert cloud_task.done() and session.session_task.done()
            assert await asyncio.wait_for(cloud[0][0].read(), 1) == b""
            assert coord.dosing_tracker._store.saved["channels"]["chlorine"]["accumulated_runtime_seconds"] == 321
            assert coord.backwash_tracker._store.saved["state"]["last_backwash_timestamp"] == "2026-09-01T12:00:00+00:00"
            assert coord.forecast._store.saved["channels"]
        await no_background_tasks()
    asyncio.run(run())


def test_stop_blocked_cloud_drain(modules, monkeypatch):
    async def run():
        async with running(modules, cloud=True) as (coord, connect, cloud):
            _, writer = await connect()
            await until(lambda: cloud and next(iter(coord._sessions.values())).cloud_writer)
            session = next(iter(coord._sessions.values()))
            entered = asyncio.Event()

            async def blocked_drain():
                entered.set()
                await asyncio.Future()

            # Keep both real TCP connections; inject deterministic write backpressure.
            monkeypatch.setattr(session.cloud_writer, "drain", blocked_drain)
            writer.write(FRAME)
            await writer.drain()
            await asyncio.wait_for(entered.wait(), 1)
            await asyncio.wait_for(coord.async_stop(), 2)
            assert session.session_task.done()
            assert not coord._sessions
            assert session.cloud_writer is None
        await no_background_tasks()
    asyncio.run(run())


@pytest.mark.parametrize("target", ["gateway", "cloud"])
def test_stop_bounds_real_writer_close(modules, monkeypatch, target):
    monkeypatch.setattr(modules["coordinator"], "_CLOSE_TIMEOUT", 0.03)

    async def run():
        async with running(modules, cloud=True) as (coord, connect, cloud):
            await connect()
            await until(lambda: cloud and next(iter(coord._sessions.values())).cloud_writer)
            session = next(iter(coord._sessions.values()))
            writer = session.gateway_writer if target == "gateway" else session.cloud_writer

            async def blocked_close():
                await asyncio.Future()

            monkeypatch.setattr(writer, "wait_closed", blocked_close)
            await asyncio.wait_for(coord.async_stop(), 1)
            assert writer.transport.is_closing()
            assert session.session_task.done()
        await no_background_tasks()
    asyncio.run(run())


def test_late_accepted_connection_is_rejected(modules):
    async def run():
        async with running(modules) as (coord, connect, _):
            await connect()
            accepted = []
            # A real accepted socket whose callback is delayed past stop.
            server = await asyncio.start_server(lambda r, w: accepted.append((r, w)), "127.0.0.1", 0)
            reader, writer = await asyncio.open_connection("127.0.0.1", server.sockets[0].getsockname()[1])
            try:
                await until(lambda: accepted)
                await coord.async_stop()
                coord._accept_client(*accepted[0])
                assert await asyncio.wait_for(reader.read(), 1) == b""
                assert not coord._sessions and coord.clients == 0
            finally:
                writer.transport.abort()
                accepted[0][1].transport.abort()
                server.close()
                await asyncio.wait_for(server.wait_closed(), 1)
        await no_background_tasks()
    asyncio.run(run())


def test_accepted_session_not_yet_started_is_closed(modules, monkeypatch):
    async def run():
        async with running(modules) as (coord, _, _):
            # Block the session coroutine at its first instruction, after the
            # synchronous accept callback registered its socket.
            entered = asyncio.Event()

            async def delayed_handler(*args):
                entered.set()
                await asyncio.Future()

            monkeypatch.setattr(coord, "_handle_client", delayed_handler)
            reader, writer = await asyncio.open_connection("127.0.0.1", coord.server.sockets[0].getsockname()[1])
            try:
                await asyncio.wait_for(entered.wait(), 1)
                assert coord.clients == 1
                await asyncio.wait_for(coord.async_stop(), 1)
                assert await asyncio.wait_for(reader.read(), 1) == b""
                assert not coord._sessions
            finally:
                writer.transport.abort()
        await no_background_tasks()
    asyncio.run(run())


def test_concurrent_stop_and_repeated_unload_share_cleanup(modules, monkeypatch):
    async def run():
        async with running(modules) as (coord, connect, _):
            await connect()
            session = next(iter(coord._sessions.values()))
            save = AsyncMock(wraps=coord.dosing_tracker.async_save)
            monkeypatch.setattr(coord.dosing_tracker, "async_save", save)
            init = modules["init"]
            hass = unload_hass(init, coord)
            entry = types.SimpleNamespace(entry_id="entry-1")
            await asyncio.wait_for(asyncio.gather(
                coord.async_stop(), init.async_unload_entry(hass, entry),
                init.async_unload_entry(hass, entry), coord.async_stop(),
            ), 2)
            assert await init.async_unload_entry(hass, entry)
            await coord.async_stop()
            assert save.await_count == 1
            assert session.session_task.done()
            assert hass.data[init.DOMAIN] == {}
        await no_background_tasks()
    asyncio.run(run())


def test_cancelled_unload_propagates_and_can_be_joined(modules, monkeypatch):
    async def run():
        async with running(modules) as (coord, connect, _):
            await connect()
            entered, release = asyncio.Event(), asyncio.Event()
            save = coord.dosing_tracker.async_save

            async def delayed_save():
                entered.set()
                await release.wait()
                await save()

            monkeypatch.setattr(coord.dosing_tracker, "async_save", delayed_save)
            init = modules["init"]
            hass = unload_hass(init, coord)
            entry = types.SimpleNamespace(entry_id="entry-1")
            task = asyncio.create_task(init.async_unload_entry(hass, entry))
            await asyncio.wait_for(entered.wait(), 1)
            task.cancel()
            try:
                with pytest.raises(asyncio.CancelledError):
                    await task
                assert hass.data[init.DOMAIN][entry.entry_id] is coord
                assert not coord._stop_task.cancelled()
            finally:
                release.set()
            assert await asyncio.wait_for(init.async_unload_entry(hass, entry), 1)
            assert coord._stop_task.done()
            assert coord.dosing_tracker._store.saved is not None
        await no_background_tasks()
    asyncio.run(run())


def test_cancelled_cloud_cleanup_is_not_swallowed(modules, monkeypatch):
    async def run():
        async with running(modules, cloud=True) as (coord, connect, cloud):
            await connect()
            await until(lambda: cloud and next(iter(coord._sessions.values())).cloud_writer)
            session = next(iter(coord._sessions.values()))
            original = session.cloud_discard_task
            original.cancel()
            await asyncio.gather(original, return_exceptions=True)
            cancelling = asyncio.Event()

            async def slow_discard():
                try:
                    await asyncio.Future()
                finally:
                    cancelling.set()
                    await asyncio.sleep(10)

            session.cloud_discard_task = asyncio.create_task(slow_discard())
            await asyncio.sleep(0)
            cleanup = asyncio.create_task(coord._close_cloud_forwarding(session))
            await asyncio.wait_for(cancelling.wait(), 1)
            cleanup.cancel()
            with pytest.raises(asyncio.CancelledError):
                await cleanup
            await coord.async_stop()
        await no_background_tasks()
    asyncio.run(run())


def test_stop_event_registration_and_unload_callback_removal(modules):
    async def run():
        init = modules["init"]
        listeners, unload_callbacks = {}, []

        def listen_once(event, handler):
            listeners[event] = handler
            return lambda: listeners.pop(event, None)

        class ConfigEntries:
            async def async_forward_entry_setups(self, entry, platforms):
                pass

            async def async_unload_platforms(self, entry, platforms):
                for cancel in unload_callbacks:
                    cancel()
                return True

        entry = types.SimpleNamespace(
            entry_id="entry-1", data={"listen_host": "127.0.0.1", "listen_port": 0, "forward_enabled": False}, options={},
            async_on_unload=unload_callbacks.append,
            add_update_listener=lambda fn: lambda: None,
        )
        hass = types.SimpleNamespace(data={}, bus=types.SimpleNamespace(async_listen_once=listen_once), config_entries=ConfigEntries())
        assert await init.async_setup_entry(hass, entry)
        coord = hass.data[init.DOMAIN][entry.entry_id]
        reader, writer = await asyncio.open_connection("127.0.0.1", coord.server.sockets[0].getsockname()[1])
        try:
            await until(lambda: coord.clients == 1)
            await asyncio.wait_for(listeners[init.EVENT_HOMEASSISTANT_STOP](object()), 2)
            assert await init.async_unload_entry(hass, entry)
            assert not listeners
            assert await asyncio.wait_for(reader.read(), 1) == b""
        finally:
            writer.transport.abort()
            await coord.async_stop()
        await no_background_tasks()
    asyncio.run(run())


def test_stop_during_cloud_connect(modules, monkeypatch):
    async def run():
        async with running(modules, cloud=True) as (coord, connect, _):
            original_open = asyncio.open_connection
            entered = asyncio.Event()

            async def blocked_cloud_open(host, port, *args, **kwargs):
                if port == coord.options["forward_port"]:
                    entered.set()
                    await asyncio.Future()
                return await original_open(host, port, *args, **kwargs)

            monkeypatch.setattr(asyncio, "open_connection", blocked_cloud_open)
            await connect()
            await asyncio.wait_for(entered.wait(), 1)
            session = next(iter(coord._sessions.values()))
            await asyncio.wait_for(coord.async_stop(), 1)
            assert session.session_task.done()
            assert not coord._sessions
        await no_background_tasks()
    asyncio.run(run())


def test_server_wait_closed_is_bounded(modules, monkeypatch):
    monkeypatch.setattr(modules["coordinator"], "_CLOSE_TIMEOUT", 0.03)

    async def run():
        async with running(modules) as (coord, connect, _):
            await connect()
            server = coord.server
            original_wait = server.wait_closed

            async def blocked_wait():
                await asyncio.Future()

            monkeypatch.setattr(server, "wait_closed", blocked_wait)
            await asyncio.wait_for(coord.async_stop(), 1)
            await asyncio.wait_for(original_wait(), 1)
            assert not coord._sessions
            assert coord.dosing_tracker._store.saved is not None
        await no_background_tasks()
    asyncio.run(run())


def test_shutdown_joins_handler_already_cleaning_up(modules, monkeypatch):
    async def run():
        async with running(modules, cloud=True) as (coord, connect, cloud):
            _, client = await connect()
            await until(lambda: cloud and next(iter(coord._sessions.values())).cloud_writer)
            session = next(iter(coord._sessions.values()))
            writer = session.cloud_writer
            original_wait = writer.wait_closed
            entered, release = asyncio.Event(), asyncio.Event()
            waits = 0

            async def delayed_wait():
                nonlocal waits
                waits += 1
                entered.set()
                await release.wait()
                await original_wait()

            monkeypatch.setattr(writer, "wait_closed", delayed_wait)
            client.close()
            await asyncio.wait_for(entered.wait(), 1)
            assert session.closing
            stop = asyncio.create_task(coord.async_stop())
            await asyncio.sleep(0)
            release.set()
            await asyncio.wait_for(stop, 1)
            assert waits == 1
            assert session.session_task.done()
            assert not coord._sessions
        await no_background_tasks()
    asyncio.run(run())
