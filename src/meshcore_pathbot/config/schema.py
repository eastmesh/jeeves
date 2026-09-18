"""Pydantic configuration models."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class ConnectionConfig(BaseModel):
    """MeshCore device connection settings."""

    type: Literal["serial", "tcp", "ble"] = "serial"
    serial_port: str | None = None
    serial_baud: int = 115200
    tcp_host: str | None = None
    tcp_port: int = 5000
    ble_address: str | None = None
    auto_reconnect: bool = True
    max_reconnect_attempts: int = 10
    tcp_health_check_interval: int = Field(default=30, ge=0)
    tcp_reconnect_delay: int = Field(default=5, ge=1)


class ChannelConfig(BaseModel):
    """Per-channel settings including which commands are enabled."""

    id: int = Field(ge=0, le=7)
    name: str = ""
    enabled_commands: list[str] = Field(
        default_factory=lambda: ["trace", "ping", "paths", "prefix"],
    )
    rate_limit_enabled: bool = True
    rate_limit_seconds: int = Field(default=120, ge=1)


class BotConfig(BaseModel):
    """Bot behavior settings."""

    node_name: str = ""
    # Optional MeshCore flood scope for all bot-originated messages.
    # Empty preserves the radio's existing scope behaviour.
    flood_scope: str = ""
    channel: int = Field(default=2, ge=0, le=7)
    channels: list[ChannelConfig] = Field(default_factory=list)
    repeaters_file: Path = Path("repeaters.db")
    ignore_list: list[str] = Field(default_factory=lambda: ["jeeves"])
    home_repeater_name: str = ""
    home_repeater_prefix: str = ""
    lat: float = 0.0
    lon: float = 0.0
    weather_home_name: str = "Hampton Park"
    weather_home_lat: float = -38.0291
    weather_home_lon: float = 145.2591
    weather_home_postcode: str = "3976"
    openweathermap_api_key: str = ""

    # Daily forecast settings
    daily_forecast_enabled: bool = False
    daily_forecast_channels: list[int] = Field(default_factory=list)
    daily_forecast_hour: int = Field(default=6, ge=0, le=23)
    timezone: str = ""  # IANA timezone (e.g. "Australia/Melbourne"); empty = system local time

    def get_active_channels(self) -> list[ChannelConfig]:
        """Return configured channels, falling back to legacy single channel."""
        if self.channels:
            return self.channels
        return [ChannelConfig(id=self.channel)]

    def is_command_enabled(self, channel_id: int, command: str) -> bool:
        """Check if a command is enabled on the given channel."""
        for ch in self.get_active_channels():
            if ch.id == channel_id:
                return command in ch.enabled_commands
        return False

    def is_rate_limit_enabled(self, channel_id: int) -> bool:
        """Check whether command rate limiting is enabled on a channel."""
        for ch in self.get_active_channels():
            if ch.id == channel_id:
                return ch.rate_limit_enabled
        return True

    def get_rate_limit_seconds(self, channel_id: int) -> int:
        """Return per-user command rate limit timeout for a channel."""
        for ch in self.get_active_channels():
            if ch.id == channel_id:
                return ch.rate_limit_seconds
        return 120


class WebConfig(BaseModel):
    """Web dashboard settings."""

    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = Field(default=8075, ge=1, le=65535)


class GuestWebConfig(BaseModel):
    """Read-only guest web dashboard settings."""

    enabled: bool = False
    host: str = "0.0.0.0"
    port: int = Field(default=8076, ge=1, le=65535)
    ping_channels: list[int] = Field(default_factory=list)


class LoggingConfig(BaseModel):
    """Logging settings."""

    level: str = "INFO"
    file: Path | None = None


class AppConfig(BaseModel):
    """Top-level application configuration."""

    connection: ConnectionConfig = Field(default_factory=ConnectionConfig)
    bot: BotConfig = Field(default_factory=BotConfig)
    web: WebConfig = Field(default_factory=WebConfig)
    guest_web: GuestWebConfig = Field(default_factory=GuestWebConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    config_path: Path | None = None
