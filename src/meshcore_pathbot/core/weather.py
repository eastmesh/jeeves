"""Weather service: fetch current conditions and forecasts via OpenWeatherMap."""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.parse
import urllib.request
from collections import OrderedDict
from datetime import datetime
from numbers import Real

log = logging.getLogger("pathbot.weather")

_OPENWEATHER_BASE = "https://api.openweathermap.org/data/2.5"
_GEO_BASE = "https://api.openweathermap.org/geo/1.0"


def _api_key_param(api_key: str) -> str:
    """Return a URL-encoded OpenWeatherMap API key parameter or raise if missing."""
    key = api_key.strip()
    if not key:
        raise ValueError("OpenWeatherMap API key is not configured")
    return urllib.parse.urlencode({"appid": key})


def _postcode_param(postcode: str) -> str:
    """Return an OpenWeatherMap AU postcode query value."""
    return urllib.parse.quote(f"{postcode.strip()},AU")


def _format_desc(weather: list | None) -> str:
    """Return a compact human-readable OpenWeatherMap description."""
    if not weather:
        return "Weather"
    desc = weather[0].get("description") if isinstance(weather[0], dict) else None
    return str(desc or "Weather").capitalize()


def _format_temp(value: object) -> str:
    """Return a rounded integer-like temperature string."""
    if isinstance(value, Real):
        return f"{float(value):.0f}"
    return "?" if value is None else str(value)


async def _fetch_json(url: str, headers: dict[str, str] | None = None) -> dict | list:
    """Fetch JSON from *url* in a thread-pool executor (non-blocking)."""
    def _do_fetch() -> dict | list:
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _do_fetch)


async def get_coords_for_postcode(postcode: str, api_key: str = "") -> tuple[float, float, str] | None:
    """Return (lat, lon, place_name) for an Australian postcode, or None on failure."""
    url = f"{_GEO_BASE}/zip?zip={_postcode_param(postcode)}&{_api_key_param(api_key)}"
    try:
        data = await _fetch_json(url)
        if not isinstance(data, dict) or "lat" not in data or "lon" not in data:
            return None
        lat = float(data["lat"])
        lon = float(data["lon"])
        name = str(data.get("name") or postcode)
        return lat, lon, name
    except Exception as exc:
        log.warning("OpenWeatherMap postcode lookup failed for %s: %s", postcode, exc)
        return None


async def get_current_weather_for_postcode(postcode: str, api_key: str) -> dict:
    """Return raw OpenWeatherMap current weather for an Australian postcode."""
    url = (
        f"{_OPENWEATHER_BASE}/weather?zip={_postcode_param(postcode)}"
        f"&units=metric&{_api_key_param(api_key)}"
    )
    data = await _fetch_json(url)
    if not isinstance(data, dict):
        raise ValueError("Unexpected response from OpenWeatherMap")
    return data


async def get_forecast_for_postcode(postcode: str, api_key: str) -> dict:
    """Return raw OpenWeatherMap 5 day / 3 hour forecast for an Australian postcode."""
    url = (
        f"{_OPENWEATHER_BASE}/forecast?zip={_postcode_param(postcode)}"
        f"&units=metric&{_api_key_param(api_key)}"
    )
    data = await _fetch_json(url)
    if not isinstance(data, dict):
        raise ValueError("Unexpected response from OpenWeatherMap")
    return data


async def get_current_weather(lat: float, lon: float, api_key: str = "") -> dict:
    """Return raw OpenWeatherMap current weather for coordinates."""
    url = (
        f"{_OPENWEATHER_BASE}/weather?lat={lat}&lon={lon}"
        f"&units=metric&{_api_key_param(api_key)}"
    )
    data = await _fetch_json(url)
    if not isinstance(data, dict):
        raise ValueError("Unexpected response from OpenWeatherMap")
    return data


async def get_forecast(lat: float, lon: float, api_key: str = "") -> dict:
    """Return raw OpenWeatherMap forecast for coordinates."""
    url = (
        f"{_OPENWEATHER_BASE}/forecast?lat={lat}&lon={lon}"
        f"&units=metric&{_api_key_param(api_key)}"
    )
    data = await _fetch_json(url)
    if not isinstance(data, dict):
        raise ValueError("Unexpected response from OpenWeatherMap")
    return data


async def current_weather_reply(sender: str, lat: float, lon: float, location_name: str, api_key: str = "") -> str:
    """Fetch current weather and return a formatted bot reply string."""
    return _format_current_reply(sender, await get_current_weather(lat, lon, api_key), location_name)


async def current_weather_reply_for_postcode(sender: str, postcode: str, api_key: str) -> str:
    """Fetch current weather for an Australian postcode and return a bot reply."""
    data = await get_current_weather_for_postcode(postcode, api_key)
    location_name = str(data.get("name") or postcode)
    return _format_current_reply(sender, data, location_name)


def _format_current_reply(sender: str, data: dict, location_name: str) -> str:
    main = data.get("main", {})
    temp = main.get("temp")
    desc = _format_desc(data.get("weather"))
    wind_speed = data.get("wind", {}).get("speed")

    if temp is None:
        return f"@[{sender}] Weather data unavailable for {location_name}"

    parts = [f"{location_name}: {_format_temp(temp)}°C, {desc}"]
    if wind_speed is not None:
        parts.append(f"wind {_format_temp(float(wind_speed) * 3.6)} km/h")
    return f"@[{sender}] {', '.join(parts)}"


async def forecast_reply(sender: str, lat: float, lon: float, location_name: str, api_key: str = "") -> str:
    """Fetch a 3-day forecast and return a formatted bot reply string."""
    return _format_forecast_reply(sender, await get_forecast(lat, lon, api_key), location_name)


async def forecast_reply_for_postcode(sender: str, postcode: str, api_key: str) -> str:
    """Fetch a 3-day forecast for an Australian postcode and return a bot reply."""
    data = await get_forecast_for_postcode(postcode, api_key)
    location_name = str(data.get("city", {}).get("name") or postcode)
    return _format_forecast_reply(sender, data, location_name)


def _forecast_item_local_datetime(item: dict) -> datetime | None:
    """Return a forecast item's timestamp in the system local timezone."""
    timestamp = item.get("dt")
    if isinstance(timestamp, Real):
        return datetime.fromtimestamp(float(timestamp))

    dt_txt = str(item.get("dt_txt") or "")
    if not dt_txt:
        return None
    try:
        return datetime.strptime(dt_txt, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _daily_forecast_parts(data: dict) -> list[str]:
    grouped: OrderedDict[str, dict[str, object]] = OrderedDict()
    for item in data.get("list", []):
        if not isinstance(item, dict):
            continue
        local_dt = _forecast_item_local_datetime(item)
        if local_dt is None:
            continue
        date_key = local_dt.date().isoformat()
        entry = grouped.setdefault(date_key, {"mins": [], "maxes": [], "desc": None, "midday_delta": 99})
        main = item.get("main", {})
        if isinstance(main, dict):
            if isinstance(main.get("temp_min"), Real):
                entry["mins"].append(float(main["temp_min"]))  # type: ignore[union-attr]
            if isinstance(main.get("temp_max"), Real):
                entry["maxes"].append(float(main["temp_max"]))  # type: ignore[union-attr]
        delta = abs(local_dt.hour - 12)
        if delta < int(entry["midday_delta"]):
            entry["midday_delta"] = delta
            entry["desc"] = _format_desc(item.get("weather"))

    parts: list[str] = []
    for date_key, entry in list(grouped.items())[:3]:
        try:
            day_label = datetime.strptime(date_key, "%Y-%m-%d").strftime("%a")
        except ValueError:
            day_label = date_key
        mins = entry["mins"]
        maxes = entry["maxes"]
        lo_s = _format_temp(min(mins) if mins else None)  # type: ignore[arg-type]
        hi_s = _format_temp(max(maxes) if maxes else None)  # type: ignore[arg-type]
        desc = str(entry.get("desc") or "Weather")
        parts.append(f"{day_label} {lo_s}-{hi_s}°C {desc}")
    return parts


def _format_forecast_reply(sender: str, data: dict, location_name: str) -> str:
    day_parts = _daily_forecast_parts(data)
    if not day_parts:
        return f"@[{sender}] Forecast unavailable for {location_name}"
    return f"@[{sender}] {location_name} 3-day: {', '.join(day_parts)}"


async def forecast_broadcast(lat: float, lon: float, location_name: str, api_key: str = "") -> str:
    """Fetch a 3-day forecast and return a formatted broadcast string (no @sender prefix)."""
    data = await get_forecast(lat, lon, api_key)
    day_parts = _daily_forecast_parts(data)
    if not day_parts:
        return f"Forecast unavailable for {location_name}"
    return f"{location_name} 3-day forecast: {', '.join(day_parts)}"
