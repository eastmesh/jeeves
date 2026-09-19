"""Pydantic configuration models."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Values that explicitly request "no region scope" (mirrors the MeshCore SDK's
# reset tokens). Lets a channel opt out of a global ``bot.flood_scope``.
UNSCOPED_TOKENS = frozenset({"*", "0", "none"})


def _clean_scope(value: object) -> str:
    """Strip a configured scope and reject values that cannot be a region name."""
    if value is None:
        return ""
    scope = str(value).strip()
    if any(ch.isspace() for ch in scope):
        raise ValueError("scope must not contain whitespace")
    return scope


def dedupe_channels(channels: list[ChannelConfig]) -> list[ChannelConfig]:
    """Drop repeated channel IDs, keeping the first entry (the one lookups already use)."""
    seen: set[int] = set()
    unique: list[ChannelConfig] = []
    for ch in channels:
        if ch.id not in seen:
            seen.add(ch.id)
            unique.append(ch)
    return unique


def normalize_scope(value: str) -> str:
    """Return the region to apply, or ``""`` for explicitly unscoped/unset."""
    scope = value.strip()
    return "" if scope.lower() in UNSCOPED_TOKENS else scope


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
    # Optional MeshCore region for bot-originated sends on this channel.
    # Empty inherits bot.flood_scope; "*" forces unscoped on this channel.
    scope: str = ""

    _validate_scope = field_validator("scope", mode="before")(
        lambda cls, v: _clean_scope(v)
    )


class BotConfig(BaseModel):
    """Bot behavior settings."""

    node_name: str = ""
    # Optional MeshCore flood scope for all bot-originated messages.
    # Fallback for channels without their own ``scope``. Empty (with no channel
    # scopes) leaves the radio's scope untouched.
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

    _validate_flood_scope = field_validator("flood_scope", mode="before")(
        lambda cls, v: _clean_scope(v)
    )

    @field_validator("channels", mode="after")
    @classmethod
    def _dedupe_channels(cls, v: list[ChannelConfig]) -> list[ChannelConfig]:
        # Duplicate IDs would subscribe duplicate handlers (duplicate replies);
        # keep the first entry for backward compatibility with old configs.
        return dedupe_channels(v)

    def scope_management_enabled(self) -> bool:
        """True when any channel or the global fallback configures a scope."""
        return bool(self.flood_scope) or any(ch.scope for ch in self.channels)

    def resolve_scope(self, channel_id: int) -> str:
        """Region for sends on a channel; ``""`` means unscoped.

        Precedence: channel scope, then ``flood_scope``, then unscoped.
        """
        for ch in self.get_active_channels():
            if ch.id == channel_id and ch.scope:
                return normalize_scope(ch.scope)
        return normalize_scope(self.flood_scope)

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
