"""Tests for the help bot command."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace


from meshcore_pathbot.config.schema import AppConfig, ChannelConfig
from meshcore_pathbot.core.bot import PathBot
from meshcore_pathbot.events.bus import EventBus


class DummyDB:
    pass


class DummyStore:
    async def add(self, *args, **kwargs):
        return None

    async def add_event(self, *args, **kwargs):
        return None

    def get_paths_for_peer(self, peer: str):
        return []


class DummyCommands:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_chan_msg(self, channel_id: int, text: str):
        self.sent.append((channel_id, text))
        return SimpleNamespace(type=None, payload={})


def _make_bot(enabled_commands: list[str], channel_id: int = 2) -> tuple[PathBot, DummyCommands]:
    config = AppConfig()
    config.bot.channels = [
        ChannelConfig(id=channel_id, enabled_commands=enabled_commands, rate_limit_enabled=False)
    ]
    bot = PathBot(config=config, db=DummyDB(), bus=EventBus(), message_store=DummyStore())
    commands = DummyCommands()
    bot._mc = SimpleNamespace(commands=commands)
    return bot, commands


def test_help_disabled_by_default():
    """help is not in the default enabled_commands so it should be ignored."""
    config = AppConfig()
    bot = PathBot(config=config, db=DummyDB(), bus=EventBus(), message_store=DummyStore())
    commands = DummyCommands()
    bot._mc = SimpleNamespace(commands=commands)

    event = SimpleNamespace(payload={"text": "Alice: help", "channel_idx": 2})
    asyncio.run(bot._on_channel_msg(event))

    assert len(commands.sent) == 0


def test_help_lists_enabled_commands():
    """help should reply with the enabled commands for the channel."""
    bot, commands = _make_bot(["trace", "ping", "help"])

    event = SimpleNamespace(payload={"text": "Alice: help", "channel_idx": 2})
    asyncio.run(bot._on_channel_msg(event))

    assert len(commands.sent) == 1
    reply = commands.sent[0][1]
    assert "trace" in reply
    assert "ping" in reply
    assert "help" in reply


def test_help_on_wrong_channel_ignored():
    """help enabled on ch3 but message on ch2 should be ignored."""
    bot, commands = _make_bot(enabled_commands=["help"], channel_id=3)

    event = SimpleNamespace(payload={"text": "Alice: help", "channel_idx": 2})
    asyncio.run(bot._on_channel_msg(event))

    assert len(commands.sent) == 0


def test_help_respects_rate_limit():
    """Second help command within the rate-limit window should be ignored."""
    config = AppConfig()
    config.bot.channels = [
        ChannelConfig(id=2, enabled_commands=["help"], rate_limit_enabled=True, rate_limit_seconds=120)
    ]
    bot = PathBot(config=config, db=DummyDB(), bus=EventBus(), message_store=DummyStore())
    commands = DummyCommands()
    bot._mc = SimpleNamespace(commands=commands)

    event = SimpleNamespace(payload={"text": "Alice: help", "channel_idx": 2})
    asyncio.run(bot._on_channel_msg(event))
    asyncio.run(bot._on_channel_msg(event))

    assert len(commands.sent) == 1
