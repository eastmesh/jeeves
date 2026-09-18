from __future__ import annotations

from types import SimpleNamespace

import pytest

from meshcore_pathbot.config.loader import load_config
from meshcore_pathbot.config.schema import AppConfig, ConnectionConfig
from meshcore_pathbot.core.bot import PathBot
from meshcore_pathbot.web.routes.settings import ALL_COMMANDS
from meshcore_pathbot.events.bus import EventBus


class DummyDB:
    pass


class DummyStore:
    pass


def test_cli_tcp_selects_tcp_connection_and_port() -> None:
    args = SimpleNamespace(
        serial=None,
        tcp="192.168.1.100",
        ble=None,
        port=5001,
        baud=None,
        channel=None,
        repeaters_file=None,
        ignore=[],
        web_host=None,
        web_port=None,
        no_web=False,
        debug=False,
    )

    config = load_config(None, args)

    assert config.connection.type == "tcp"
    assert config.connection.tcp_host == "192.168.1.100"
    assert config.connection.tcp_port == 5001


def test_settings_command_list_includes_multipath() -> None:
    assert "multipath" in ALL_COMMANDS


@pytest.mark.asyncio
async def test_bot_connects_to_tcp_companion_with_reconnect_options(monkeypatch) -> None:
    calls: list[dict] = []

    async def fake_create_tcp(host: str, port: int, **kwargs):
        calls.append({"host": host, "port": port, **kwargs})
        return SimpleNamespace()

    monkeypatch.setattr("meshcore_pathbot.core.bot.MeshCore.create_tcp", fake_create_tcp)

    config = AppConfig(
        connection=ConnectionConfig(
            type="tcp",
            tcp_host="meshcore.local",
            tcp_port=5001,
            auto_reconnect=True,
            max_reconnect_attempts=7,
        )
    )
    config.logging.level = "DEBUG"
    bot = PathBot(config=config, db=DummyDB(), bus=EventBus(), message_store=DummyStore())

    await bot._connect()

    assert calls == [
        {
            "host": "meshcore.local",
            "port": 5001,
            "debug": True,
            "auto_reconnect": True,
            "max_reconnect_attempts": 7,
        }
    ]


@pytest.mark.asyncio
async def test_bot_requires_tcp_host_for_tcp_connection() -> None:
    config = AppConfig(connection=ConnectionConfig(type="tcp", tcp_host=None))
    bot = PathBot(config=config, db=DummyDB(), bus=EventBus(), message_store=DummyStore())

    with pytest.raises(ValueError, match="TCP host not configured"):
        await bot._connect()


class FakeCommands:
    def __init__(self, result=None, exc: Exception | None = None) -> None:
        self.result = result
        self.exc = exc

    async def send_appstart(self):
        if self.exc is not None:
            raise self.exc
        return self.result


class FakeMeshCore:
    def __init__(self, *, is_connected: bool = True, result=None, exc: Exception | None = None) -> None:
        self.is_connected = is_connected
        self.commands = FakeCommands(result=result, exc=exc)
        self.stopped_fetching = False
        self.disconnected = False

    async def stop_auto_message_fetching(self) -> None:
        self.stopped_fetching = True

    async def disconnect(self) -> None:
        self.disconnected = True


@pytest.mark.asyncio
async def test_tcp_health_check_uses_appstart() -> None:
    config = AppConfig(connection=ConnectionConfig(type="tcp", tcp_host="meshcore.local"))
    bot = PathBot(config=config, db=DummyDB(), bus=EventBus(), message_store=DummyStore())
    bot._mc = FakeMeshCore(result=SimpleNamespace(type=None))

    assert await bot._tcp_health_check() is True


@pytest.mark.asyncio
async def test_tcp_health_check_fails_when_stale_or_command_errors() -> None:
    config = AppConfig(connection=ConnectionConfig(type="tcp", tcp_host="meshcore.local"))
    bot = PathBot(config=config, db=DummyDB(), bus=EventBus(), message_store=DummyStore())

    bot._mc = FakeMeshCore(is_connected=False, result=SimpleNamespace(type=None))
    assert await bot._tcp_health_check() is False

    bot._mc = FakeMeshCore(exc=ConnectionError("stale TCP socket"))
    assert await bot._tcp_health_check() is False


@pytest.mark.asyncio
async def test_reconnect_tcp_companion_replaces_connection(monkeypatch) -> None:
    config = AppConfig(
        connection=ConnectionConfig(
            type="tcp",
            tcp_host="meshcore.local",
            max_reconnect_attempts=2,
            tcp_reconnect_delay=1,
        )
    )
    bot = PathBot(config=config, db=DummyDB(), bus=EventBus(), message_store=DummyStore())
    old_mc = FakeMeshCore()
    new_mc = FakeMeshCore()
    bot._mc = old_mc
    initialized: list[FakeMeshCore] = []

    async def fake_connect():
        return new_mc

    async def fake_initialize():
        initialized.append(bot._mc)

    monkeypatch.setattr(bot, "_connect", fake_connect)
    monkeypatch.setattr(bot, "_initialize_connected_meshcore", fake_initialize)

    await bot._reconnect_tcp_companion()

    assert old_mc.stopped_fetching is True
    assert old_mc.disconnected is True
    assert bot._mc is new_mc
    assert initialized == [new_mc]
