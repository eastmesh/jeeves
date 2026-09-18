"""Guest dashboard route — ping responses landing page."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..dependencies import get_bot, get_message_store

router = APIRouter()


@router.get("/")
async def guest_dashboard(
    request: Request,
    bot=Depends(get_bot),
    store=Depends(get_message_store),
):
    """Show recent ping responses using configured guest channel filters."""
    templates = request.app.state.templates
    active_channels = bot.config.bot.get_active_channels()
    ping_enabled_channel_ids = [ch.id for ch in active_channels if "ping" in ch.enabled_commands]
    configured_channels = [
        ch for ch in bot.config.guest_web.ping_channels if ch in ping_enabled_channel_ids
    ]
    selected_channels = configured_channels or ping_enabled_channel_ids

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "request": request,
            "ping_responses": store.get_recent_ping_responses(
                channels=selected_channels,
                count=10,
            ),
        },
    )
