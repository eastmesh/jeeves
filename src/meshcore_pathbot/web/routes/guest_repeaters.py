"""Guest repeaters route — read-only database viewer (no delete)."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Request

from ..dependencies import get_db

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
