"""Guest API routes — limited SSE streams and read-only endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sse_starlette import EventSourceResponse

from ...events.types import AppEvent
from ..dependencies import get_bot, get_bus
from ..sse import sse_stream

router = APIRouter()


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
