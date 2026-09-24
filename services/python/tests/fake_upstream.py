"""In-memory CDS + APDS servers implementing conformance/fixtures.json "fake_upstream" rules."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

REPO = Path(__file__).resolve().parents[3]
EXAMPLES = REPO / "examples"
CONFORMANCE = REPO / "conformance"

PLACES_PARAMS = {"page", "latitude", "longitude", "radius", "type", "expand"}
SPECS_PARAMS = {"page"}
ASSIGNED_PARAMS = {"page", "right_spec", "credential_id", "credential_type"}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2
    return 2 * 6_371_008.8 * math.asin(math.sqrt(a))


def _json(status: int, body: Any) -> httpx.Response:
    return httpx.Response(status, json=body)


def _paged(items: list[dict[str, Any]], page_size: int, page_raw: str | None) -> httpx.Response:
    page = int(page_raw or "1")
    offset = (page - 1) * page_size
    return _json(200, {
        "data": items[offset: offset + page_size],
        "meta": {"referenceInstant": 0, "offset": offset, "pageSize": page_size, "total": len(items)},
    })


class FakeUpstream:
    def __init__(self, fixtures: dict[str, Any]) -> None:
        cfg = fixtures["config"]
        self.cds_host = urlparse(cfg["CDS_BASE_URL"]).netloc
        self.apds_host = urlparse(cfg["APDS_BASE_URL"]).netloc
        self.apds_prefix = urlparse(cfg["APDS_BASE_URL"]).path.rstrip("/")
        load = lambda files: [load_json(EXAMPLES / f) for f in files]  # noqa: E731
        self.zones = load(fixtures["cds"]["zones"])
        self.areas = load(fixtures["cds"]["areas"])
        self.policies = load(fixtures["cds"]["policies"])
        self.elements = load(fixtures["apds"]["elements"])
        self.specs = load(fixtures["apds"]["right_specs"])
        self.assigned = load(fixtures["apds"]["assigned_rights"])
        self.requests: list[httpx.Request] = []

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.method != "GET":
            return _json(405, {})
        if request.url.host == self.cds_host:
            return self._cds(request.url.path)
        if request.url.host == self.apds_host and request.url.path.startswith(self.apds_prefix):
            return self._apds(request.url.path[len(self.apds_prefix):], dict(request.url.params))
        return _json(404, {})

    def _cds(self, path: str) -> httpx.Response:
        parts = [p for p in path.split("/") if p]
        if len(parts) < 2 or parts[0] != "curbs":
            return _json(404, {})
        collections = {"zones": (self.zones, "curb_zone_id"), "areas": (self.areas, "curb_area_id"), "policies": (self.policies, "curb_policy_id")}
        if parts[1] not in collections:
            return _json(404, {})
        items, key = collections[parts[1]]
        if len(parts) == 2:
            return _json(200, {"version": "1.1", "data": {parts[1]: items}})
        match = next((i for i in items if i[key] == parts[2]), None)
        return _json(200, {"version": "1.1", "data": match}) if match else _json(404, {})

    def _apds(self, path: str, params: dict[str, str]) -> httpx.Response:
        parts = [p for p in path.split("/") if p]
        if parts == ["places"]:
            return self._places(params)
        if len(parts) == 2 and parts[0] == "places":
            return self._by_id(self.elements, parts[1])
        if parts == ["rights", "specs"]:
            return _json(400, {}) if set(params) - SPECS_PARAMS else _paged(self.specs, 2, params.get("page"))
        if len(parts) == 3 and parts[:2] == ["rights", "specs"]:
            return self._by_id(self.specs, parts[2])
        if parts == ["rights", "assigned"]:
            return self._assigned(params)
        return _json(404, {})

    @staticmethod
    def _by_id(items: list[dict[str, Any]], item_id: str) -> httpx.Response:
        match = next((i for i in items if i["id"] == item_id), None)
        return _json(200, match) if match else _json(404, {"status": "error", "code": 404})

    def _places(self, params: dict[str, str]) -> httpx.Response:
        if set(params) - PLACES_PARAMS:
            return _json(400, {})
        items = self.elements
        if "type" in params:
            types = set(params["type"].split(","))
            items = [e for e in items if e.get("type") in types]
        if "radius" in params:
            lat, lng, radius = float(params["latitude"]), float(params["longitude"]), float(params["radius"])
            items = [e for e in items if self._within(e, lat, lng, radius)]
        return _paged(items, 2, params.get("page"))

    @staticmethod
    def _within(element: dict[str, Any], lat: float, lng: float, radius: float) -> bool:
        points = element.get("indicativePointLocation") or []
        if not points:
            return False
        e_lng, e_lat = points[0]["coordinates"][:2]
        return _haversine(lat, lng, e_lat, e_lng) <= radius

    def _assigned(self, params: dict[str, str]) -> httpx.Response:
        if set(params) - ASSIGNED_PARAMS:
            return _json(400, {})
        specs = set(params.get("right_spec", "").split(",")) if "right_spec" in params else None
        types = set(params.get("credential_type", "").split(",")) if "credential_type" in params else None
        wanted = params.get("credential_id")

        def matches(right: dict[str, Any]) -> bool:
            if specs is not None and right["rightSpecification"]["id"] not in specs:
                return False
            if wanted is None:
                return True
            return any(
                c["identifier"]["id"] == wanted and (types is None or c["type"] in types)
                for c in right["rightHolder"]["credentials"]
            )

        return _paged([r for r in self.assigned if matches(r)], 100, params.get("page"))
