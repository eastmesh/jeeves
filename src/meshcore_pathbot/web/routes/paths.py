"""Paths route — path resolution tool."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Form, Request

from ..dependencies import get_bot, get_message_store

router = APIRouter()


@router.get("/paths")
async def paths_page(request: Request, store=Depends(get_message_store)):
    templates = request.app.state.templates
    peers = store.get_unique_peers()
    return templates.TemplateResponse(
        request,
        "paths.html",
        {"request": request, "hops": None, "raw_path": "", "peers": peers},
    )


@router.post("/paths/resolve")
async def resolve_path(
    request: Request,
    raw_path: str = Form(""),
    selected_repeaters: str = Form("{}"),
    bot=Depends(get_bot),
):
    templates = request.app.state.templates
    raw_path = raw_path.strip().lower()

    try:
        preferred_repeaters = json.loads(selected_repeaters or "{}")
        if not isinstance(preferred_repeaters, dict):
            preferred_repeaters = {}
    except json.JSONDecodeError:
        preferred_repeaters = {}

    hops = bot.resolver.resolve_detailed(raw_path, preferred_repeaters=preferred_repeaters) if raw_path else []
    resolved_str = bot.resolver.resolve(raw_path, preferred_repeaters=preferred_repeaters) if raw_path else ""
    raw_str = bot.resolver.raw(raw_path) if raw_path else ""

    return templates.TemplateResponse(
        request,
        "partials/path_display.html",
        {
            "request": request,
            "hops": hops,
            "resolved_str": resolved_str,
            "raw_str": raw_str,
        },
    )


@router.post("/paths/search")
async def search_user_paths(
    request: Request,
    peer_name: str = Form(""),
    bot=Depends(get_bot),
    store=Depends(get_message_store),
):
    templates = request.app.state.templates
    peer_name = peer_name.strip()

    results = []
    if peer_name:
        raw_paths = store.get_paths_for_peer(peer_name)
        for raw_path in raw_paths:
            if raw_path:
                hops = bot.resolver.resolve_detailed(raw_path)
                resolved_str = bot.resolver.resolve(raw_path)
                raw_str = bot.resolver.raw(raw_path)
            else:
                hops = []
                resolved_str = "Direct"
                raw_str = "(no hops)"
            results.append(
                {
                    "raw_path": raw_path,
                    "hops": hops,
                    "resolved_str": resolved_str,
                    "raw_str": raw_str,
                }
            )

    return templates.TemplateResponse(
        request,
        "partials/user_paths.html",
        {
            "request": request,
            "peer_name": peer_name,
            "results": results,
        },
    )
