# AGENTS.md

## Project overview
- This repository hosts the MeshCore PathBot web/admin + guest interfaces.
- Keep changes focused and minimal; prefer small, explicit patches over broad refactors.

## Development workflow
- Run targeted tests for changed behavior first, then run full `pytest` when practical.
- Keep UI behavior consistent between admin and guest pages when the feature applies to both.

## Web/UI conventions
- Templates live in `src/meshcore_pathbot/web/templates/`.
- Guest templates live in `src/meshcore_pathbot/web/templates/guest/`.
- Shared path rendering partials are under `src/meshcore_pathbot/web/templates/partials/`; prefer enhancing shared partials instead of duplicating logic.
- Prefer lightweight, framework-free JavaScript in templates/static files.

## Path handling
- MeshCore paths may use 1-byte or multibyte hop hashes; preserve full multibyte hop segments where available instead of truncating to first-byte compatibility prefixes.
- When formatting stored or displayed paths, use hash-size-aware helpers/shared resolver logic so admin pages, guest pages, `trace`, `ping`, `paths`, and `multipath` stay consistent.

## Data retention
- Repeater cleanup is daily and uses a 7-day retention window.
- If touching cleanup logic, keep retention-related UI copy and backend behavior aligned.

## Adding new bot commands
To add a new bot command, touch these files in order:
1. `src/meshcore_pathbot/config/schema.py` — Add any new config fields to `BotConfig`.
2. `src/meshcore_pathbot/web/routes/settings.py` — Add the command name to `ALL_COMMANDS` and add any new form fields.
3. `src/meshcore_pathbot/web/templates/settings.html` — Add a column to the Channel Management table and any new fieldset for related config.
4. `src/meshcore_pathbot/core/bot.py` — Detect the command keyword in `_on_channel_msg` (use `startswith` for commands that accept arguments) and add a handler block.
5. `config.example.toml` — Document any new config keys.
6. Add tests in `tests/`.

New commands default to **off** — do not add them to `ChannelConfig.enabled_commands` default list. Operators must explicitly enable them per channel.

## Weather commands
The bot supports `weather [postcode]` and `forecast [postcode]` commands:
- Without a postcode, uses the configured home location (`bot.weather_home_name/lat/lon`; defaults to Hampton Park, VIC).
- With a postcode, geocodes it via Nominatim (OpenStreetMap) then fetches from Open-Meteo.
- Both APIs are free and require no API key.
- HTTP calls use Python's `urllib.request` via `asyncio` executor — no extra runtime dependency.
- Both commands are off by default; enable per channel in the Channel Management settings table.
