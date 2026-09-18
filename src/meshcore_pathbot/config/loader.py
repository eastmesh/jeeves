"""TOML config loading with CLI override merging."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .schema import AppConfig

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]


def load_toml(path: Path) -> dict:
    """Read and parse a TOML config file."""
    with open(path, "rb") as f:
        return tomllib.load(f)


def merge_cli_overrides(config_dict: dict, args: argparse.Namespace) -> dict:
    """Overlay CLI arguments onto the config dict. Only non-None values are applied."""
    conn = config_dict.setdefault("connection", {})
    bot = config_dict.setdefault("bot", {})
    web = config_dict.setdefault("web", {})
    log = config_dict.setdefault("logging", {})

    # Connection type and params
    if getattr(args, "serial", None):
        conn["type"] = "serial"
        conn["serial_port"] = args.serial
    elif getattr(args, "tcp", None):
        conn["type"] = "tcp"
        conn["tcp_host"] = args.tcp
    elif getattr(args, "ble", None) is not None:
        conn["type"] = "ble"
        if args.ble:
            conn["ble_address"] = args.ble

    if getattr(args, "port", None) is not None:
        conn["tcp_port"] = args.port
    if getattr(args, "baud", None) is not None:
        conn["serial_baud"] = args.baud

    # Bot settings
    if getattr(args, "channel", None) is not None:
        bot["channel"] = args.channel
    if getattr(args, "repeaters_file", None) is not None:
        bot["repeaters_file"] = str(args.repeaters_file)
    if getattr(args, "ignore", None):
        existing = bot.get("ignore_list", [])
        bot["ignore_list"] = existing + [n.lower() for n in args.ignore]

    # Web settings
    if getattr(args, "web_host", None) is not None:
        web["host"] = args.web_host
    if getattr(args, "web_port", None) is not None:
        web["port"] = args.web_port
    if getattr(args, "no_web", False):
        web["enabled"] = False

    # Logging
    if getattr(args, "debug", False):
        log["level"] = "DEBUG"

    return config_dict


def load_config(config_path: Path | None, args: argparse.Namespace) -> AppConfig:
    """Load config from TOML file, merge CLI overrides, and validate."""
    config_dict: dict = {}

    if config_path and config_path.exists():
        config_dict = load_toml(config_path)

    config_dict = merge_cli_overrides(config_dict, args)

    config = AppConfig(**config_dict)
    config.config_path = config_path
    return config
