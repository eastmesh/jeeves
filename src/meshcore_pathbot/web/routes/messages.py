"""Messages route — live message feed with persistent history."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..dependencies import get_bot, get_message_store

router = APIRouter()


@router.get("/messages")
async def messages_page(
    request: Request,
    bot=Depends(get_bot),
    store=Depends(get_message_store),
):
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "messages.html",
        {
            "request": request,
            "stats": bot.stats.to_dict(),
            "messages": store.get_all(),
        },
    )
