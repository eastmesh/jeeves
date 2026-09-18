"""Stats route — detailed statistics."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..dependencies import get_bot, get_db

router = APIRouter()


@router.get("/stats")
async def stats_page(
    request: Request,
    bot=Depends(get_bot),
    db=Depends(get_db),
):
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "stats.html",
        {
            "request": request,
            "stats": bot.stats.to_dict(),
            "db_stats": db.stats(),
            "connected": bot.is_connected,
        },
    )
