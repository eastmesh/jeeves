"""Write configuration back to TOML file."""

from __future__ import annotations

from pathlib import Path

import tomli_w

from .schema import AppConfig


def _strip_none(d: dict) -> dict:
    """Recursively remove keys whose value is ``None``.

    TOML has no null type, so None values must be omitted entirely.
    """
    cleaned: dict = {}
    for key, value in d.items():
        if value is None:
            continue
        if isinstance(value, dict):
            cleaned[key] = _strip_none(value)
        else:
            cleaned[key] = value
    return cleaned


def save_config(config: AppConfig, path: Path | None = None) -> None:
    """Serialize the current config to a TOML file."""
    target = path or config.config_path
    if target is None:
        raise ValueError("No config file path specified")

    data = config.model_dump(exclude={"config_path"}, mode="json")

    # Convert Path objects to strings for TOML serialization
    if "bot" in data and "repeaters_file" in data["bot"]:
        data["bot"]["repeaters_file"] = str(data["bot"]["repeaters_file"])
    if "logging" in data and data["logging"].get("file"):
        data["logging"]["file"] = str(data["logging"]["file"])

    # TOML has no null type — drop any keys with None values
    data = _strip_none(data)

    with open(target, "wb") as f:
        tomli_w.dump(data, f)
