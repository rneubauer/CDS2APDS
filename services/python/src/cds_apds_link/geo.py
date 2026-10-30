"""Small, dependency-free geometry helpers (docs/03-link-service.md §3.4)."""
from __future__ import annotations

import math
from typing import Any

from .jsonutil import is_number

EARTH_RADIUS_M = 6_371_008.8


def round_half_up(value: float) -> int:
    return math.floor(value + 0.5)


def round6(value: float) -> float:
    return math.floor(value * 1_000_000 + 0.5) / 1_000_000


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def _is_position(p: Any) -> bool:
    return isinstance(p, list) and len(p) >= 2 and is_number(p[0]) and is_number(p[1])


def _positions(geometry: Any) -> list[list[float]]:
    if not isinstance(geometry, dict):
        raise ValueError("geometry is not an object")
    kind, coords = geometry.get("type"), geometry.get("coordinates")
    if kind == "Point":
        points = [coords]
    elif kind == "LineString":
        points = coords
    elif kind == "Polygon":
        if not isinstance(coords, list) or not coords or not isinstance(coords[0], list):
            raise ValueError("polygon has no rings")
        ring = coords[0]
        points = ring[:-1] if len(ring) > 1 and ring[0] == ring[-1] else ring
    else:
        raise ValueError(f"unsupported geometry type {kind!r}")
    if not isinstance(points, list) or not points:
        raise ValueError("geometry has no positions")
    for p in points:
        if not _is_position(p):
            raise ValueError("invalid position")
    return points


def centroid(geometry: Any) -> tuple[float, float]:
    """Mean vertex of a GeoJSON Point/LineString/Polygon, returned as (lat, lng) rounded to 6 dp."""
    points = _positions(geometry)
    lng = sum(p[0] for p in points) / len(points)
    lat = sum(p[1] for p in points) / len(points)
    return round6(lat), round6(lng)


def point_of(location: Any) -> tuple[float, float] | None:
    """(lat, lng) of the first APDS PointLocation in a list, or None."""
    if not isinstance(location, list) or not location:
        return None
    first = location[0]
    if not isinstance(first, dict) or first.get("type") != "Point":
        return None
    coords = first.get("coordinates")
    if _is_position(coords):
        return float(coords[1]), float(coords[0])
    return None
