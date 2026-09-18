"""Settings route — configuration editor."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Form, Request

from ...config.schema import AppConfig, ChannelConfig
from ...config.writer import save_config
from ...events.bus import EventBus
from ...events.types import AppEvent
from ..dependencies import get_bus, get_config

router = APIRouter()

ALL_COMMANDS = [
    "trace",
    "ping",
    "paths",
    "multipath",
    "prefix",
    "weather",
    "wx",
    "forecast",
    "fx",
    "help",
]


@router.get("/settings")
async def settings_page(
    request: Request,
    config: AppConfig = Depends(get_config),
):
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "request": request,
            "config": config,
            "all_commands": ALL_COMMANDS,
        },
    )


@router.post("/settings")
async def save_settings(
    request: Request,
    config: AppConfig = Depends(get_config),
    bus: EventBus = Depends(get_bus),
    connection_type: str = Form("serial"),
    serial_port: str = Form(""),
    serial_baud: int = Form(115200),
    tcp_host: str = Form(""),
    tcp_port: int = Form(5000),
    tcp_health_check_interval: int = Form(30),
    tcp_reconnect_delay: int = Form(5),
    ble_address: str = Form(""),
    node_name: str = Form(""),
    channel: int = Form(2),
    channels_json: str = Form("[]"),
    ignore_list: str = Form(""),
    home_repeater_name: str = Form(""),
    home_repeater_prefix: str = Form(""),
    bot_lat: float = Form(0.0),
    bot_lon: float = Form(0.0),
    weather_home_name: str = Form("Hampton Park"),
    weather_home_lat: float = Form(-38.0291),
    weather_home_lon: float = Form(145.2591),
    weather_home_postcode: str = Form("3976"),
    openweathermap_api_key: str = Form(""),
    daily_forecast_enabled: str = Form(""),
    daily_forecast_channels: list[int] | None = Form(default=None),
    daily_forecast_hour: int = Form(6),
    timezone: str = Form(""),
    web_host: str = Form("0.0.0.0"),
    web_port: int = Form(8075),
    guest_web_enabled: str = Form(""),
    guest_web_host: str = Form("0.0.0.0"),
    guest_web_port: int = Form(8076),
    guest_ping_channels: list[int] | None = Form(default=None),
    log_level: str = Form("INFO"),
):
    templates = request.app.state.templates

    # Update config in-place
    config.connection.type = connection_type  # type: ignore[assignment]
    config.connection.serial_port = serial_port or None
    config.connection.serial_baud = serial_baud
    config.connection.tcp_host = tcp_host or None
    config.connection.tcp_port = tcp_port
    config.connection.tcp_health_check_interval = max(0, tcp_health_check_interval)
    config.connection.tcp_reconnect_delay = max(1, tcp_reconnect_delay)
    config.connection.ble_address = ble_address or None
    config.bot.node_name = node_name.strip()
    config.bot.channel = channel
    config.bot.ignore_list = [
        s.strip() for s in ignore_list.split(",") if s.strip()
    ]
    config.bot.home_repeater_name = home_repeater_name.strip()
    config.bot.home_repeater_prefix = home_repeater_prefix.strip().lower()
    config.bot.lat = bot_lat
    config.bot.lon = bot_lon
    config.bot.weather_home_name = weather_home_name.strip()
    config.bot.weather_home_lat = weather_home_lat
    config.bot.weather_home_lon = weather_home_lon
    config.bot.weather_home_postcode = weather_home_postcode.strip()
    new_openweathermap_api_key = openweathermap_api_key.strip()
    if new_openweathermap_api_key:
        config.bot.openweathermap_api_key = new_openweathermap_api_key
    config.bot.daily_forecast_channels = sorted(set(daily_forecast_channels or []))
    config.bot.daily_forecast_enabled = (daily_forecast_enabled == "true") and bool(config.bot.daily_forecast_channels)
    config.bot.daily_forecast_hour = max(0, min(23, daily_forecast_hour))
    config.bot.timezone = timezone.strip()
    config.web.host = web_host
    config.web.port = web_port
    config.guest_web.enabled = guest_web_enabled == "true"
    config.guest_web.host = guest_web_host
    config.guest_web.port = guest_web_port
    config.logging.level = log_level

    # Parse channels from JSON submitted by the form
    try:
        channels_data = json.loads(channels_json)
    except (json.JSONDecodeError, TypeError):
        channels_data = []

    parsed_channels: list[ChannelConfig] = []
    for ch in channels_data:
        try:
            ch_id = int(ch.get("id", 0))
            ch_name = str(ch.get("name", "")).strip()
            ch_cmds = ch.get("enabled_commands", ALL_COMMANDS)
            ch_rate_limit_enabled = bool(ch.get("rate_limit_enabled", True))
            ch_rate_limit_seconds = int(ch.get("rate_limit_seconds", 120))
            if not isinstance(ch_cmds, list):
                ch_cmds = ALL_COMMANDS
            # Validate command names
            ch_cmds = [c for c in ch_cmds if c in ALL_COMMANDS]
            parsed_channels.append(ChannelConfig(
                id=ch_id,
                name=ch_name,
                enabled_commands=ch_cmds,
                rate_limit_enabled=ch_rate_limit_enabled,
                rate_limit_seconds=ch_rate_limit_seconds,
            ))
        except (ValueError, TypeError):
            continue

    config.bot.channels = parsed_channels

    active_channel_ids = {ch.id for ch in config.bot.get_active_channels() if "ping" in ch.enabled_commands}
    selected_guest_ping_channels = sorted({ch for ch in (guest_ping_channels or []) if ch in active_channel_ids})
    config.guest_web.ping_channels = selected_guest_ping_channels

    # Save to file if a config path is set
    if config.config_path:
        try:
            save_config(config, config.config_path)
        except Exception as e:
            return templates.TemplateResponse(
                request,
                "partials/toast.html",
                {"request": request, "message": f"Error saving: {e}", "type": "error"},
            )

    await bus.publish(AppEvent.CONFIG_UPDATE, {"saved": True})

    return templates.TemplateResponse(
        request,
        "partials/toast.html",
        {"request": request, "message": "Settings saved (restart required for channel changes)", "type": "success"},
    )
