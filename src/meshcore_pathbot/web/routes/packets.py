"""Packets route — packet activity over time."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..dependencies import get_message_store

router = APIRouter()


@router.get("/packets")
async def packets_page(
    request: Request,
    store=Depends(get_message_store),
):
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "packets.html",
        {
            "request": request,
            "totals": store.get_24h_totals(),
        },
    )
