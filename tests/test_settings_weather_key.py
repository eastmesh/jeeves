"""Tests for OpenWeatherMap API key handling in settings."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from meshcore_pathbot.config.schema import AppConfig
from meshcore_pathbot.events.bus import EventBus
from meshcore_pathbot.web.routes.settings import save_settings


class DummyTemplates:
    def TemplateResponse(self, request, template_name, context):
        return {"template_name": template_name, "context": context}


def _request():
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(templates=DummyTemplates())))


def test_settings_template_does_not_render_saved_openweathermap_key():
    template = Path("src/meshcore_pathbot/web/templates/settings.html").read_text()

    assert 'name="openweathermap_api_key" value=""' in template
    assert 'value="{{ config.bot.openweathermap_api_key }}"' not in template


def _save_settings_kwargs(openweathermap_api_key: str) -> dict:
    return {
        "connection_type": "serial",
        "serial_port": "",
        "serial_baud": 115200,
        "tcp_host": "",
        "tcp_port": 5000,
        "tcp_health_check_interval": 30,
        "tcp_reconnect_delay": 5,
        "ble_address": "",
        "node_name": "",
        "channel": 2,
        "channels_json": "[]",
        "ignore_list": "",
        "home_repeater_name": "",
        "home_repeater_prefix": "",
        "bot_lat": 0.0,
        "bot_lon": 0.0,
        "weather_home_name": "Hampton Park",
        "weather_home_lat": -38.0291,
        "weather_home_lon": 145.2591,
        "weather_home_postcode": "3976",
        "openweathermap_api_key": openweathermap_api_key,
        "daily_forecast_enabled": "",
        "daily_forecast_channels": None,
        "daily_forecast_hour": 6,
        "timezone": "",
        "web_host": "0.0.0.0",
        "web_port": 8075,
        "guest_web_enabled": "",
        "guest_web_host": "0.0.0.0",
        "guest_web_port": 8076,
        "guest_ping_channels": None,
        "log_level": "INFO",
    }


def test_blank_openweathermap_key_submission_preserves_existing_key():
    config = AppConfig()
    config.bot.openweathermap_api_key = "existing-key"

    asyncio.run(save_settings(
        _request(),
        config,
        EventBus(),
        **_save_settings_kwargs(openweathermap_api_key=""),
    ))

    assert config.bot.openweathermap_api_key == "existing-key"


def test_nonblank_openweathermap_key_submission_replaces_existing_key():
    config = AppConfig()
    config.bot.openweathermap_api_key = "existing-key"

    asyncio.run(save_settings(
        _request(),
        config,
        EventBus(),
        **_save_settings_kwargs(openweathermap_api_key=" new-key "),
    ))

    assert config.bot.openweathermap_api_key == "new-key"
