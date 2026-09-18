"""Overlaps route — shows repeaters with colliding prefix IDs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ...core.geo import haversine, has_location
from ..dependencies import get_db

router = APIRouter()


def _annotate_collision_distances(collisions: list[dict]) -> list[dict]:
    """Annotate overlaps with distance metadata for display.

    Adds, for each repeater, `closest_distance_km` (distance to nearest other
    repeater in the same prefix group) and, for each group,
    `max_distance_km` (greatest pairwise distance in the group).
    """
    annotated_groups: list[dict] = []

    for group in collisions:
        repeaters = [dict(r) for r in group.get("repeaters", [])]
        max_distance_km = 0.0

        for i, repeater in enumerate(repeaters):
            if not has_location(repeater):
                repeater["closest_distance_km"] = None
                continue

            distances: list[float] = []
            for j, other in enumerate(repeaters):
                if i == j or not has_location(other):
                    continue
                km = haversine(repeater["lat"], repeater["lon"], other["lat"], other["lon"])
                distances.append(km)
                if km > max_distance_km:
                    max_distance_km = km

            repeater["closest_distance_km"] = min(distances) if distances else None

        annotated_groups.append({
            **group,
            "repeaters": repeaters,
            "max_distance_km": max_distance_km if max_distance_km > 0 else None,
        })

    return annotated_groups


def _filter_collisions_by_prefix(collisions: list[dict], prefix_query: str) -> list[dict]:
    """Filter overlap groups by a prefix search query."""
    query = prefix_query.strip().lower()
    if not query:
        return collisions
    return [group for group in collisions if str(group.get("prefix", "")).lower().startswith(query)]


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
