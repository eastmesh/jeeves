"""Repeaters route — database viewer/editor."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ...events.bus import EventBus
from ...events.types import AppEvent
from ..dependencies import get_bus, get_db

router = APIRouter()


@router.get("/repeaters")
async def repeaters_page(
    request: Request,
    db=Depends(get_db),
):
    templates = request.app.state.templates
    now = int(time.time())
    cleanup_every_seconds = 24 * 60 * 60
    seconds_until_cleanup = cleanup_every_seconds - (now % cleanup_every_seconds)
    return templates.TemplateResponse(
        request,
        "repeaters.html",
        {
            "request": request,
            "repeaters": db.get_all(),
            "stats": db.stats(),
            "retention_days": 7,
            "seconds_until_cleanup": seconds_until_cleanup,
        },
    )


@router.delete("/repeaters/{public_key}")
async def delete_repeater(
    public_key: str,
    db=Depends(get_db),
    bus: EventBus = Depends(get_bus),
):
    deleted = await db.delete(public_key)
    if deleted:
        await bus.publish(AppEvent.REPEATER_DELETE, {"public_key": public_key})
    # Return empty content so htmx removes the row
    return HTMLResponse("")
