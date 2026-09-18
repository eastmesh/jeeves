"""Guest overlaps route — read-only prefix collision viewer."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from .overlaps import _annotate_collision_distances, _filter_collisions_by_prefix
from ..dependencies import get_db

router = APIRouter()


@router.get("/overlaps")
async def overlaps_page(
    request: Request,
    prefix: str = Query(default=""),
    db=Depends(get_db),
):
    templates = request.app.state.templates
    collisions = _annotate_collision_distances(db.get_collisions())
    filtered_collisions = _filter_collisions_by_prefix(collisions, prefix)
    total_affected = sum(len(g["repeaters"]) for g in collisions)
    filtered_total_affected = sum(len(g["repeaters"]) for g in filtered_collisions)
    return templates.TemplateResponse(
        request,
        "overlaps.html",
        {
            "request": request,
            "collisions": filtered_collisions,
            "collision_count": len(filtered_collisions),
            "total_affected": total_affected,
            "filtered_total_affected": filtered_total_affected,
            "prefix_query": prefix.strip().lower(),
        },
    )
