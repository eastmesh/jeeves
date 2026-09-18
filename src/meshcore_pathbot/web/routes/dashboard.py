"""Dashboard route — main landing page."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..dependencies import get_bot, get_db, get_message_store

router = APIRouter()


@router.get("/")
async def dashboard(
    request: Request,
    bot=Depends(get_bot),
    db=Depends(get_db),
    store=Depends(get_message_store),
):
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "request": request,
            "stats": bot.stats.to_dict(),
            "db_stats": db.stats(),
            "connected": bot.is_connected,
            "channels": bot.config.bot.get_active_channels(),
            "totals_24h": store.get_24h_totals(),
        },
    )
