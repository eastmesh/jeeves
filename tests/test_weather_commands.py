"""Tests for weather and forecast bot commands."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


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
    config.bot.weather_home_name = "Hampton Park"
    config.bot.weather_home_lat = -38.0291
    config.bot.weather_home_lon = 145.2591
    config.bot.weather_home_postcode = "3976"
    config.bot.openweathermap_api_key = "test-key"

    bot = PathBot(config=config, db=DummyDB(), bus=EventBus(), message_store=DummyStore())
    commands = DummyCommands()
    bot._mc = SimpleNamespace(commands=commands)
    return bot, commands


# ── weather command disabled (default) ────────────────────────────────────────

def test_weather_command_disabled_by_default():
    """weather is not in the default enabled_commands so it should be ignored."""
    config = AppConfig()
    # Use the schema default — no explicit channels
    bot = PathBot(config=config, db=DummyDB(), bus=EventBus(), message_store=DummyStore())
    commands = DummyCommands()
    bot._mc = SimpleNamespace(commands=commands)

    event = SimpleNamespace(payload={"text": "Alice: weather 3000", "channel_idx": 2})
    asyncio.run(bot._on_channel_msg(event))

    assert len(commands.sent) == 0


def test_forecast_command_disabled_by_default():
    """forecast is not in the default enabled_commands so it should be ignored."""
    config = AppConfig()
    bot = PathBot(config=config, db=DummyDB(), bus=EventBus(), message_store=DummyStore())
    commands = DummyCommands()
    bot._mc = SimpleNamespace(commands=commands)

    event = SimpleNamespace(payload={"text": "Alice: forecast", "channel_idx": 2})
    asyncio.run(bot._on_channel_msg(event))

    assert len(commands.sent) == 0


# ── weather command enabled ────────────────────────────────────────────────────

def test_weather_without_postcode_uses_home_postcode():
    """weather with no postcode should use the configured home postcode."""
    bot, commands = _make_bot(["weather"])

    fake_reply = "@[Alice] Hampton Park: 19°C, Partly cloudy"

    with patch(
        "meshcore_pathbot.core.weather.current_weather_reply_for_postcode",
        new=AsyncMock(return_value=fake_reply),
    ) as mock_weather:
        event = SimpleNamespace(payload={"text": "Alice: weather", "channel_idx": 2})
        asyncio.run(bot._on_channel_msg(event))

    mock_weather.assert_called_once_with("Alice", "3976", "test-key")
    assert len(commands.sent) == 1
    assert "Hampton Park" in commands.sent[0][1]


def test_weather_with_non_postcode_text_is_ignored():
    """weather followed by non-postcode text should not trigger the command."""
    bot, commands = _make_bot(["weather"])

    event = SimpleNamespace(payload={"text": "Alice: weather tomorrow", "channel_idx": 2})
    asyncio.run(bot._on_channel_msg(event))

    assert len(commands.sent) == 0


def test_weather_with_postcode_calls_geocode():
    """weather 3000 should use the postcode and reply with that location."""
    bot, commands = _make_bot(["weather"])

    fake_reply = "@[Alice] Melbourne: 20°C, Partly cloudy, wind 10 km/h"

    with patch(
        "meshcore_pathbot.core.weather.current_weather_reply_for_postcode",
        new=AsyncMock(return_value=fake_reply),
    ):
        event = SimpleNamespace(payload={"text": "Alice: weather 3000", "channel_idx": 2})
        asyncio.run(bot._on_channel_msg(event))

    assert len(commands.sent) == 1
    assert "Melbourne" in commands.sent[0][1]


def test_weather_unknown_postcode_sends_fallback():
    """weather <bad postcode> should send a postcode-specific fallback."""
    bot, commands = _make_bot(["weather"])

    with patch(
        "meshcore_pathbot.core.weather.current_weather_reply_for_postcode",
        new=AsyncMock(side_effect=Exception("not found")),
    ):
        event = SimpleNamespace(payload={"text": "Alice: weather 9999", "channel_idx": 2})
        asyncio.run(bot._on_channel_msg(event))

    assert len(commands.sent) == 1
    assert "9999" in commands.sent[0][1]


def test_weather_http_error_sends_fallback():
    """If the weather API raises an exception the bot sends a friendly fallback."""
    bot, commands = _make_bot(["weather"])

    with patch(
        "meshcore_pathbot.core.weather.current_weather_reply_for_postcode",
        new=AsyncMock(side_effect=Exception("network error")),
    ):
        event = SimpleNamespace(payload={"text": "Alice: weather 3000", "channel_idx": 2})
        asyncio.run(bot._on_channel_msg(event))

    assert len(commands.sent) == 1
    assert "unavailable" in commands.sent[0][1].lower()


def test_wx_short_command_with_postcode():
    """wx 3000 should behave like weather 3000 when wx is enabled."""
    bot, commands = _make_bot(["wx"])

    with patch(
        "meshcore_pathbot.core.weather.current_weather_reply_for_postcode",
        new=AsyncMock(return_value="@[Alice] Melbourne: 20C"),
    ) as mock_weather:
        event = SimpleNamespace(payload={"text": "Alice: wx 3000", "channel_idx": 2})
        asyncio.run(bot._on_channel_msg(event))

    mock_weather.assert_called_once_with("Alice", "3000", "test-key")
    assert commands.sent == [(2, "@[Alice] Melbourne: 20C")]

def test_wx_short_command_requires_wx_enabled():
    """wx is a separate per-channel command and should not run when only weather is enabled."""
    bot, commands = _make_bot(["weather"])

    with patch(
        "meshcore_pathbot.core.weather.current_weather_reply_for_postcode",
        new=AsyncMock(return_value="@[Alice] Melbourne: 20C"),
    ) as mock_weather:
        event = SimpleNamespace(payload={"text": "Alice: wx 3000", "channel_idx": 2})
        asyncio.run(bot._on_channel_msg(event))

    mock_weather.assert_not_called()
    assert commands.sent == []

# ── forecast command enabled ───────────────────────────────────────────────────

def test_forecast_home_location_reply():
    """forecast (no postcode) should use the configured home postcode."""
    bot, commands = _make_bot(["forecast"])

    fake_reply = "@[Alice] Hampton Park 3-day: Mon 18-25°C Partly cloudy, Tue 16-28°C Sunny, Wed 14-22°C Rainy"

    with patch(
        "meshcore_pathbot.core.weather.forecast_reply_for_postcode",
        new=AsyncMock(return_value=fake_reply),
    ):
        event = SimpleNamespace(payload={"text": "Alice: forecast", "channel_idx": 2})
        asyncio.run(bot._on_channel_msg(event))

    assert len(commands.sent) == 1
    assert "3-day" in commands.sent[0][1]


def test_forecast_with_postcode():
    """forecast 3000 should use the postcode for that location forecast."""
    bot, commands = _make_bot(["forecast"])

    fake_reply = "@[Alice] Melbourne 3-day: Mon 18-25°C Sunny"

    with patch(
        "meshcore_pathbot.core.weather.forecast_reply_for_postcode",
        new=AsyncMock(return_value=fake_reply),
    ):
        event = SimpleNamespace(payload={"text": "Alice: forecast 3000", "channel_idx": 2})
        asyncio.run(bot._on_channel_msg(event))

    assert len(commands.sent) == 1
    assert "Melbourne" in commands.sent[0][1]


def test_forecast_http_error_sends_fallback():
    """If the forecast API raises, the bot sends a friendly fallback."""
    bot, commands = _make_bot(["forecast"])

    with patch(
        "meshcore_pathbot.core.weather.forecast_reply_for_postcode",
        new=AsyncMock(side_effect=Exception("timeout")),
    ):
        event = SimpleNamespace(payload={"text": "Alice: forecast", "channel_idx": 2})
        asyncio.run(bot._on_channel_msg(event))

    assert len(commands.sent) == 1
    assert "unavailable" in commands.sent[0][1].lower()


def test_fx_short_command_without_postcode_uses_home_postcode():
    """fx should behave like forecast and default to the configured home postcode."""
    bot, commands = _make_bot(["fx"])

    with patch(
        "meshcore_pathbot.core.weather.forecast_reply_for_postcode",
        new=AsyncMock(return_value="@[Alice] Hampton Park: forecast"),
    ) as mock_forecast:
        event = SimpleNamespace(payload={"text": "Alice: FX", "channel_idx": 2})
        asyncio.run(bot._on_channel_msg(event))

    mock_forecast.assert_called_once_with("Alice", "3976", "test-key")
    assert commands.sent == [(2, "@[Alice] Hampton Park: forecast")]

# ── rate limiting applies to weather commands ──────────────────────────────────

def test_weather_respects_rate_limit():
    """Second weather command within the rate-limit window should be ignored."""
    config = AppConfig()
    config.bot.channels = [
        ChannelConfig(id=2, enabled_commands=["weather"], rate_limit_enabled=True, rate_limit_seconds=120)
    ]
    bot = PathBot(config=config, db=DummyDB(), bus=EventBus(), message_store=DummyStore())
    commands = DummyCommands()
    bot._mc = SimpleNamespace(commands=commands)

    fake_reply = "@[Alice] Melbourne: 22°C, Clear sky"

    with patch(
        "meshcore_pathbot.core.weather.current_weather_reply_for_postcode",
        new=AsyncMock(return_value=fake_reply),
    ):
        event = SimpleNamespace(payload={"text": "Alice: weather 3000", "channel_idx": 2})
        asyncio.run(bot._on_channel_msg(event))
        asyncio.run(bot._on_channel_msg(event))

    assert len(commands.sent) == 1


# ── weather and forecast on correct channel ────────────────────────────────────

def test_weather_command_on_different_channel_blocked():
    """weather command on a channel where it is not enabled should be ignored."""
    bot, commands = _make_bot(enabled_commands=["weather"], channel_id=3)

    with patch(
        "meshcore_pathbot.core.weather.current_weather_reply_for_postcode",
        new=AsyncMock(return_value="@[Alice] Hampton Park: 22°C"),
    ):
        # Send on channel 2 — but weather is only enabled on channel 3
        event = SimpleNamespace(payload={"text": "Alice: weather 3000", "channel_idx": 2})
        asyncio.run(bot._on_channel_msg(event))

    assert len(commands.sent) == 0
