"""Geographic utility functions."""

from __future__ import annotations

from math import atan2, cos, radians, sin, sqrt


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance in km between two lat/lon points."""
    r = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return r * 2 * atan2(sqrt(a), sqrt(1 - a))


def has_location(node: dict) -> bool:
    """Check if a node dict has valid (non-zero) location data."""
    return node.get("lat", 0) != 0 or node.get("lon", 0) != 0
