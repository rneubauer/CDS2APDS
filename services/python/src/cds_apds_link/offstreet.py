"""T2: nearby off-street supply for a curb zone (docs/03 §3.4, profile §2.4)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .geo import haversine_m, point_of, round_half_up
from .jsonutil import as_list, is_int, is_number
from .registry import Link


def multilingual(value: Any) -> str | None:
    if not isinstance(value, list):
        return None
    entries = [v for v in value if isinstance(v, dict) and isinstance(v.get("string"), str)]
    for entry in entries:
        if entry.get("language") == "en":
            return entry["string"]
    return entries[0]["string"] if entries else None


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    # Naive values are UTC, so records with and without an offset stay comparable.
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _latest_demand(element: dict[str, Any]) -> dict[str, Any] | None:
    ref = element.get("hierarchyElementReference")
    tables = ref.get("demandTable") if isinstance(ref, dict) else None
    records = []
    for table in as_list(tables):
        rows = table.get("demandType") if isinstance(table, dict) else None
        for record in as_list(rows):
            if isinstance(record, dict) and isinstance(record.get("recordDateTime"), str):
                try:
                    records.append((_instant(record["recordDateTime"]), record))
                except ValueError:
                    continue
    return max(records, key=lambda pair: pair[0])[1] if records else None


def spaces_total(element: dict[str, Any]) -> int | None:
    ref = element.get("hierarchyElementReference")
    supplies = ref.get("supply") if isinstance(ref, dict) else None
    for supply in as_list(supplies):
        if isinstance(supply, dict) and supply.get("supplyViewType") == "spaceView" and is_int(supply.get("supplyQuantity")):
            return supply["supplyQuantity"]
    characteristics = element.get("characteristics")
    total = characteristics.get("spacesTotal") if isinstance(characteristics, dict) else None
    return total if is_int(total) else None


def availability(element: dict[str, Any]) -> tuple[int | None, int | None, str | None]:
    """(spaces_total, spaces_available, occupancy_time) following profile §2.4."""
    total = spaces_total(element)
    demand = _latest_demand(element)
    if demand is None:
        return total, None, None
    available = None
    count, percentage = demand.get("count"), demand.get("percentage")
    if total is not None and is_int(count):
        available = max(total - count, 0)
    elif total is not None and is_number(percentage):
        available = round_half_up(total * (1 - percentage / 100))
    return total, available, demand["recordDateTime"]


def linked_place_ids(zone: dict[str, Any], links: list[Link], elements: dict[str, dict[str, Any]]) -> set[str]:
    zone_id = zone.get("curb_zone_id")
    area_ids = {a for a in as_list(zone.get("curb_area_ids")) if isinstance(a, str)}
    found: set[str] = set()
    for link in links:
        if link.kind == "supply" and (
            (link.cds.type == "CurbZone" and link.cds.id == zone_id) or (link.cds.type == "CurbArea" and link.cds.id in area_ids)
        ):
            found.add(link.apds.id)
        elif link.kind == "access" and link.cds.type == "CurbZone" and link.cds.id == zone_id:
            parent = (elements.get(link.apds.id) or {}).get("parentId")
            if isinstance(parent, dict) and isinstance(parent.get("id"), str):
                found.add(parent["id"])
    return {pid for pid in found if pid in elements and elements[pid].get("type") != "vehicularAccess"}


def access_points(place_id: str, elements: dict[str, dict[str, Any]], links: list[Link]) -> list[dict[str, Any]]:
    zone_for = {link.apds.id: link.cds.id for link in links if link.kind == "access" and link.cds.type == "CurbZone"}
    points = []
    for element in elements.values():
        parent = element.get("parentId")
        if element.get("type") == "vehicularAccess" and isinstance(parent, dict) and parent.get("id") == place_id:
            points.append({
                "id": element["id"],
                "name": multilingual(element.get("name")),
                "access_type": element.get("accessType"),
                "curb_zone_id": zone_for.get(element["id"]),
            })
    return sorted(points, key=lambda p: p["id"])


def summarize_place(
    element: dict[str, Any], origin: tuple[float, float], linked: bool,
    elements: dict[str, dict[str, Any]], links: list[Link], apds_base_url: str,
) -> dict[str, Any]:
    point = point_of(element.get("indicativePointLocation"))
    distance = round_half_up(haversine_m(origin[0], origin[1], point[0], point[1])) if point else None
    total, available, occupancy_time = availability(element)
    characteristics = element.get("characteristics")
    open_to_public = characteristics.get("openToPublic") if isinstance(characteristics, dict) else None
    return {
        "id": element["id"],
        "version": element.get("version"),
        "name": multilingual(element.get("name")),
        "linked": linked,
        "distance_m": distance,
        "spaces_total": total,
        "spaces_available": available,
        "occupancy_time": occupancy_time,
        "open_to_public": open_to_public if isinstance(open_to_public, bool) else None,
        "access_points": access_points(element["id"], elements, links),
        "apds_url": f"{apds_base_url}/places/{element['id']}",
    }


def build_summary(
    zone: dict[str, Any], origin: tuple[float, float], radius_m: int, nearby: list[dict[str, Any]],
    elements: dict[str, dict[str, Any]], links: list[Link], apds_base_url: str,
) -> dict[str, Any]:
    linked_ids = linked_place_ids(zone, links, elements)
    candidates: dict[str, dict[str, Any]] = {pid: elements[pid] for pid in linked_ids}
    for element in nearby:
        if isinstance(element.get("id"), str):
            candidates[element["id"]] = element
    places = [summarize_place(el, origin, pid in linked_ids, elements, links, apds_base_url) for pid, el in candidates.items()]
    places.sort(key=lambda p: (not p["linked"], p["distance_m"] is None, p["distance_m"] or 0, p["id"]))
    return {
        "curb_zone_id": zone.get("curb_zone_id"),
        "origin": {"lat": origin[0], "lng": origin[1]},
        "radius_m": radius_m,
        "places": places,
    }
