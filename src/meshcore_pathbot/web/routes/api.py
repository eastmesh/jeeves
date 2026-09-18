"""API routes — SSE streams and JSON endpoints."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Body, Depends, Request
from meshcore import EventType
from sse_starlette import EventSourceResponse

from ...events.types import AppEvent
from ..dependencies import get_bot, get_bus, get_db, get_message_store
from ..sse import sse_stream

log = logging.getLogger("pathbot.api")

router = APIRouter()


@router.get("/messages/stream")
async def messages_stream(request: Request, bus=Depends(get_bus)):
    """SSE stream for live message updates."""
    return EventSourceResponse(
        sse_stream(request, bus, AppEvent.MSG_IN, AppEvent.MSG_OUT)
    )


@router.get("/stats/stream")
async def stats_stream(request: Request, bus=Depends(get_bus)):
    """SSE stream for stats updates."""
    return EventSourceResponse(
        sse_stream(
            request,
            bus,
            AppEvent.STATS_UPDATE,
            AppEvent.BOT_CONNECTED,
            AppEvent.BOT_DISCONNECTED,
        )
    )


@router.get("/repeaters/stream")
async def repeaters_stream(request: Request, bus=Depends(get_bus)):
    """SSE stream for repeater DB updates."""
    return EventSourceResponse(
        sse_stream(request, bus, AppEvent.REPEATER_UPDATE, AppEvent.REPEATER_DELETE)
    )


@router.get("/uptime")
async def uptime(bot=Depends(get_bot)):
    """Return formatted uptime string."""
    seconds = int(bot.stats.uptime_seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


@router.get("/messages/history")
async def messages_history(
    count: int = 200,
    store=Depends(get_message_store),
):
    """Return message history as JSON."""
    return store.get_recent(count)


@router.get("/stats/json")
async def stats_json(bot=Depends(get_bot), db=Depends(get_db)):
    """Return current stats as JSON."""
    return {
        "bot": bot.stats.to_dict(),
        "db": db.stats(),
        "connected": bot.is_connected,
        "timestamp": time.time(),
    }


@router.get("/packets/totals")
async def packets_totals(store=Depends(get_message_store)):
    """Return 24-hour packet totals by type."""
    return store.get_24h_totals()


@router.get("/packets/hourly")
async def packets_hourly(store=Depends(get_message_store)):
    """Return hourly packet counts for the last 24 hours."""
    from datetime import datetime
    data = store.get_hourly_counts(24)
    return {
        "labels": [datetime.fromtimestamp(d["hour_ts"]).strftime("%H:%M") for d in data],
        "msg_in": [d["msg_in"] for d in data],
        "msg_out": [d["msg_out"] for d in data],
    }


# ---- Radio device endpoints ----


@router.get("/radio/info")
async def radio_info(bot=Depends(get_bot)):
    """Return current radio self_info (name, freq, power, etc.)."""
    if not bot.is_connected or bot._mc is None:
        return {"error": "Radio not connected"}
    return dict(bot._mc.self_info)


@router.get("/radio/channels")
async def radio_channels(bot=Depends(get_bot)):
    """Fetch all 8 channel slots from the radio."""
    if not bot.is_connected or bot._mc is None:
        return {"error": "Radio not connected"}

    channels = []
    for idx in range(8):
        try:
            result = await bot._mc.commands.get_channel(idx)
            if result.type == EventType.CHANNEL_INFO:
                info = result.payload
                secret_bytes = info.get("channel_secret")
                secret_hex = secret_bytes.hex() if isinstance(secret_bytes, (bytes, bytearray)) else ""
                masked_secret = f"{secret_hex[:6]}…{secret_hex[-4:]}" if len(secret_hex) >= 12 else ("••••" if secret_hex else "")
                channels.append({
                    "channel_idx": info.get("channel_idx", idx),
                    "channel_name": info.get("channel_name", ""),
                    "channel_secret_hex": masked_secret,
                    "channel_hash": info.get("channel_hash", ""),
                })
            else:
                channels.append({"channel_idx": idx, "channel_name": "", "channel_secret_hex": "", "channel_hash": "", "error": str(result.payload)})
        except Exception as e:
            log.warning(f"Failed to get channel {idx}: {e}")
            channels.append({"channel_idx": idx, "channel_name": "", "channel_secret_hex": "", "channel_hash": "", "error": str(e)})
    return channels


@router.post("/radio/name")
async def set_radio_name(bot=Depends(get_bot), name: str = Body(..., embed=True)):
    """Set the radio device name."""
    if not bot.is_connected or bot._mc is None:
        return {"error": "Radio not connected"}
    result = await bot._mc.commands.set_name(name)
    if result.type == EventType.ERROR:
        return {"error": str(result.payload)}
    return {"ok": True, "name": name}


@router.post("/radio/tx_power")
async def set_radio_tx_power(bot=Depends(get_bot), tx_power: int = Body(..., embed=True)):
    """Set the radio TX power."""
    if not bot.is_connected or bot._mc is None:
        return {"error": "Radio not connected"}
    result = await bot._mc.commands.set_tx_power(tx_power)
    if result.type == EventType.ERROR:
        return {"error": str(result.payload)}
    return {"ok": True, "tx_power": tx_power}


@router.post("/radio/coords")
async def set_radio_coords(
    bot=Depends(get_bot),
    lat: float = Body(..., embed=True),
    lon: float = Body(..., embed=True),
):
    """Set the radio GPS coordinates."""
    if not bot.is_connected or bot._mc is None:
        return {"error": "Radio not connected"}
    result = await bot._mc.commands.set_coords(lat, lon)
    if result.type == EventType.ERROR:
        return {"error": str(result.payload)}
    return {"ok": True, "lat": lat, "lon": lon}


@router.post("/radio/params")
async def set_radio_params(
    bot=Depends(get_bot),
    freq: float = Body(..., embed=True),
    bw: float = Body(..., embed=True),
    sf: int = Body(..., embed=True),
    cr: int = Body(..., embed=True),
):
    """Set the radio parameters (frequency, bandwidth, spreading factor, coding rate)."""
    if not bot.is_connected or bot._mc is None:
        return {"error": "Radio not connected"}
    result = await bot._mc.commands.set_radio(freq, bw, sf, cr)
    if result.type == EventType.ERROR:
        return {"error": str(result.payload)}
    return {"ok": True, "freq": freq, "bw": bw, "sf": sf, "cr": cr}


@router.post("/radio/channel")
async def set_radio_channel(
    bot=Depends(get_bot),
    channel_idx: int = Body(..., embed=True),
    channel_name: str = Body(..., embed=True),
):
    """Set a radio channel name (secret derived from name if starts with #)."""
    if not bot.is_connected or bot._mc is None:
        return {"error": "Radio not connected"}
    result = await bot._mc.commands.set_channel(channel_idx, channel_name)
    if result.type == EventType.ERROR:
        return {"error": str(result.payload)}
    return {"ok": True, "channel_idx": channel_idx, "channel_name": channel_name}
