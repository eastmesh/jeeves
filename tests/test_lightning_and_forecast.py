"""Tests for daily forecast broadcast and weather forecast helpers."""

from __future__ import annotations

import asyncio
import datetime
import os
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from meshcore_pathbot.config.schema import AppConfig, ChannelConfig
from meshcore_pathbot.core.bot import PathBot
from meshcore_pathbot.core.weather import forecast_reply, forecast_broadcast
from meshcore_pathbot.events.bus import EventBus


class DummyDB:
    pass


class DummyStore:
    def __init__(self):
        self.records: list = []

    async def add(self, *args, **kwargs):
        self.records.append(args)

    async def add_event(self, *args, **kwargs):
        pass

    def get_paths_for_peer(self, peer: str):
        return []


class DummyCommands:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_chan_msg(self, channel_id: int, text: str):
        self.sent.append((channel_id, text))
        return SimpleNamespace(type=None, payload={})


def _make_bot(*, forecast_enabled=False, forecast_channels=None, forecast_hour=6) -> tuple[PathBot, DummyCommands, DummyStore]:
    config = AppConfig()
    config.bot.channels = [ChannelConfig(id=1, enabled_commands=["trace"], rate_limit_enabled=False)]
    config.bot.daily_forecast_enabled = forecast_enabled
    config.bot.daily_forecast_channels = forecast_channels or []
    config.bot.daily_forecast_hour = forecast_hour

    store = DummyStore()
    bot = PathBot(config=config, db=DummyDB(), bus=EventBus(), message_store=store)
    commands = DummyCommands()
    bot._mc = SimpleNamespace(commands=commands)
    return bot, commands, store


# ── forecast_broadcast (weather.py) ───────────────────────────────────────────

def test_forecast_broadcast_no_sender_prefix():
    data = {
        "list": [
            {
                "dt_txt": "2026-03-01 12:00:00",
                "main": {"temp_min": 15.0, "temp_max": 25.0},
                "weather": [{"description": "partly cloudy"}],
            }
        ]
    }
    with patch(
        "meshcore_pathbot.core.weather.get_forecast",
        new=AsyncMock(return_value=data),
    ):
        result = asyncio.run(forecast_broadcast(-38.0, 145.0, "Hampton Park"))
    assert result.startswith("Hampton Park")
    assert "@[" not in result
    assert "3-day forecast" in result


def test_forecast_broadcast_groups_days_by_system_local_time(monkeypatch):
    """Forecast dates should use the system timezone instead of UTC dt_txt dates."""
    if not hasattr(time, "tzset"):
        pytest.skip("tzset is not available on this platform")

    original_tz = os.environ.get("TZ")
    monkeypatch.setenv("TZ", "Australia/Melbourne")
    time.tzset()
    try:
        data = {
            "list": [
                {
                    "dt": int(datetime.datetime(2026, 3, 1, 15, 0, tzinfo=datetime.timezone.utc).timestamp()),
                    "dt_txt": "2026-03-01 15:00:00",
                    "main": {"temp_min": 17.0, "temp_max": 23.0},
                    "weather": [{"description": "showers"}],
                },
                {
                    "dt": int(datetime.datetime(2026, 3, 2, 1, 0, tzinfo=datetime.timezone.utc).timestamp()),
                    "dt_txt": "2026-03-02 01:00:00",
                    "main": {"temp_min": 18.0, "temp_max": 27.0},
                    "weather": [{"description": "sunny"}],
                },
            ]
        }
        with patch(
            "meshcore_pathbot.core.weather.get_forecast",
            new=AsyncMock(return_value=data),
        ):
            result = asyncio.run(forecast_broadcast(-38.0, 145.0, "Hampton Park"))
    finally:
        _restore_tz(original_tz)

    assert "Mon 17-27°C Sunny" in result
    assert "Sun " not in result


def _restore_tz(original_tz: str | None) -> None:
    if original_tz is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = original_tz
    time.tzset()


def test_forecast_broadcast_unavailable_on_empty_data():
    data = {"list": []}
    with patch(
        "meshcore_pathbot.core.weather.get_forecast",
        new=AsyncMock(return_value=data),
    ):
        result = asyncio.run(forecast_broadcast(-38.0, 145.0, "Hampton Park"))
    assert "unavailable" in result.lower()


def test_forecast_reply_tolerates_partial_daily_data():
    data = {
        "list": [
            {
                "dt_txt": "2026-03-01 12:00:00",
                "main": {"temp_min": 15.0, "temp_max": 25.0},
                "weather": [{"description": "partly cloudy"}],
            },
            {
                "dt_txt": "2026-03-02 12:00:00",
                "main": {},
                "weather": [],
            },
        ]
    }
    with patch(
        "meshcore_pathbot.core.weather.get_forecast",
        new=AsyncMock(return_value=data),
    ):
        result = asyncio.run(forecast_reply("Alice", -38.0, 145.0, "Hampton Park"))
    assert result.startswith("@[Alice] Hampton Park 3-day:")
    assert "Partly cloudy" in result
    assert "?" in result


# ── send_channel_message ───────────────────────────────────────────────────────

def test_send_channel_message_returns_true_on_success():
    bot, commands, _ = _make_bot()
    result = asyncio.run(bot.send_channel_message(1, "Hello"))
    assert result is True
    assert len(commands.sent) == 1
    assert commands.sent[0] == (1, "Hello")


def test_send_channel_message_returns_false_when_disconnected():
    bot, _, _ = _make_bot()
    bot._mc = None
    result = asyncio.run(bot.send_channel_message(1, "Hello"))
    assert result is False


def test_send_channel_message_returns_false_on_error():
    from meshcore import EventType

    bot, commands, _ = _make_bot()

    async def bad_send(ch, text):
        return SimpleNamespace(type=EventType.ERROR, payload="fail")

    bot._mc.commands.send_chan_msg = bad_send
    result = asyncio.run(bot.send_channel_message(1, "Hello"))
    assert result is False


# ── _daily_forecast_loop ───────────────────────────────────────────────────────

def test_daily_forecast_loop_sends_broadcast():
    """Daily forecast loop should send a forecast broadcast on the configured channel."""
    bot, commands, store = _make_bot(
        forecast_enabled=True, forecast_channels=[1], forecast_hour=6
    )

    fake_msg = "Hampton Park 3-day forecast: Sun 15-22°C Partly cloudy"

    async def run_one_cycle():
        sleep_calls = 0

        async def fake_sleep(seconds):
            nonlocal sleep_calls
            sleep_calls += 1
            if sleep_calls >= 2:
                raise asyncio.CancelledError()

        now_fixed = datetime.datetime(2026, 3, 1, 5, 55, 0,
                                      tzinfo=datetime.timezone.utc)

        with (
            patch("meshcore_pathbot.core.bot.weather_svc.forecast_broadcast",
                  new=AsyncMock(return_value=fake_msg)),
            patch("asyncio.sleep", new=fake_sleep),
            patch("datetime.datetime") as mock_dt,
        ):
            # Make datetime.datetime.now() return a time just before 6am
            mock_dt.now.return_value = now_fixed
            mock_dt.side_effect = lambda *a, **kw: datetime.datetime(*a, **kw)
            with pytest.raises(asyncio.CancelledError):
                await bot._daily_forecast_loop()

    asyncio.run(run_one_cycle())
    assert any(fake_msg in text for _, text in commands.sent)


def test_daily_forecast_skips_when_disconnected():
    """If the bot is not connected, the daily forecast should not try to send."""
    bot, commands, _ = _make_bot(
        forecast_enabled=True, forecast_channels=[1], forecast_hour=6
    )
    bot._mc = None  # Simulate disconnected state

    async def run_one_cycle():
        sleep_calls = 0

        async def fake_sleep(seconds):
            nonlocal sleep_calls
            sleep_calls += 1
            if sleep_calls >= 3:
                raise asyncio.CancelledError()

        with (
            patch("asyncio.sleep", new=fake_sleep),
        ):
            with pytest.raises(asyncio.CancelledError):
                await bot._daily_forecast_loop()

    asyncio.run(run_one_cycle())
    assert len(commands.sent) == 0


# ── Config schema defaults ─────────────────────────────────────────────────────

def test_daily_forecast_disabled_by_default():
    config = AppConfig()
    assert config.bot.daily_forecast_enabled is False
    assert config.bot.daily_forecast_channels == []
    assert config.bot.daily_forecast_hour == 6
