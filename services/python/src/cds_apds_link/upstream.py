"""HTTP clients for the CDS Curbs API and the APDS API.

Upstream responses are untrusted: any transport failure, non-2xx status or
malformed body becomes a 502 ``upstream_error``. Error messages carry only the
request path, never query strings (which may contain credentials).
"""
from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

import httpx

from .config import Settings
from .errors import upstream_error

MAX_PAGES = 1000


class _Http:
    def __init__(self, client: httpx.AsyncClient, base_url: str, headers: dict[str, str], label: str) -> None:
        self._client = client
        self._base = base_url
        self._headers = headers
        self._label = label

    async def get(self, path: str, params: dict[str, str] | None = None, allow_404: bool = False) -> Any:
        try:
            resp = await self._client.get(self._base + path, params=params, headers=self._headers)
        except httpx.HTTPError as exc:
            raise upstream_error(f"{self._label} request to {path} failed: {type(exc).__name__}") from None
        if resp.status_code == 404 and allow_404:
            return None
        if resp.status_code >= 400:
            raise upstream_error(f"{self._label} returned HTTP {resp.status_code} for {path}")
        try:
            return json.loads(resp.content, parse_constant=_reject_constant)
        except ValueError:
            raise upstream_error(f"{self._label} returned invalid JSON for {path}") from None


def _reject_constant(name: str) -> Any:
    """NaN and Infinity are not JSON (RFC 8259); the TypeScript service's JSON.parse rejects them too."""
    raise ValueError(f"non-standard JSON constant {name}")


def _segment(value: str) -> str:
    """Percent-encode a caller-supplied id so it stays a single path segment."""
    return quote(value, safe="")


def _require_list(value: Any, what: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise upstream_error(f"malformed {what}")
    return value


def _require_dict(value: Any, what: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise upstream_error(f"malformed {what}")
    return value


class CdsClient:
    def __init__(self, client: httpx.AsyncClient, settings: Settings) -> None:
        headers = {"Accept": "application/json"}
        if settings.cds_token:
            headers["Authorization"] = f"Bearer {settings.cds_token}"
        self._http = _Http(client, settings.cds_base_url, headers, "CDS")

    async def _collection(self, name: str, optional: bool = False) -> list[dict[str, Any]]:
        body = await self._http.get(f"/curbs/{name}", allow_404=optional)
        if body is None:
            return []
        data = _require_dict(_require_dict(body, f"CDS {name} response").get("data"), f"CDS {name} data")
        return _require_list(data.get(name, []), f"CDS {name} list")

    async def _single(self, name: str, object_id: str) -> dict[str, Any] | None:
        body = await self._http.get(f"/curbs/{name}/{_segment(object_id)}", allow_404=True)
        if body is None:
            return None
        return _require_dict(_require_dict(body, f"CDS {name} response").get("data"), f"CDS {name} object")

    async def zones(self) -> list[dict[str, Any]]:
        return await self._collection("zones")

    async def areas(self) -> list[dict[str, Any]]:
        return await self._collection("areas")

    async def policies(self) -> list[dict[str, Any]]:
        return await self._collection("policies")

    async def objects(self) -> list[dict[str, Any]]:
        return await self._collection("objects", optional=True)

    async def zone(self, zone_id: str) -> dict[str, Any] | None:
        return await self._single("zones", zone_id)

    async def policy(self, policy_id: str) -> dict[str, Any] | None:
        return await self._single("policies", policy_id)


class ApdsClient:
    def __init__(self, client: httpx.AsyncClient, settings: Settings) -> None:
        headers = {"Accept": "application/json"}
        if settings.apds_token:
            if settings.apds_auth_scheme == "mcc":
                headers["X-MCC-Access-Token"] = settings.apds_token
            else:
                headers["Authorization"] = f"Bearer {settings.apds_token}"
        self._http = _Http(client, settings.apds_base_url, headers, "APDS")

    async def _paged(self, path: str, params: dict[str, str] | None = None) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for page in range(1, MAX_PAGES + 1):
            body = _require_dict(await self._http.get(path, {**(params or {}), "page": str(page)}), f"APDS {path} list")
            batch = _require_list(body.get("data", []), f"APDS {path} data")
            meta = _require_dict(body.get("meta", {}), f"APDS {path} meta")
            items.extend(batch)
            total = meta.get("total")
            if not batch or not isinstance(total, int) or isinstance(total, bool) or len(items) >= total:
                return items
        raise upstream_error(f"APDS {path} exceeded {MAX_PAGES} pages")

    async def elements(self) -> list[dict[str, Any]]:
        return await self._paged("/places")

    async def places_near(self, lat: float, lng: float, radius_m: int) -> list[dict[str, Any]]:
        params = {
            "latitude": repr(lat),
            "longitude": repr(lng),
            "radius": str(radius_m),
            "type": "place",
            "expand": "occupancy,pointLocation,characteristics",
        }
        return await self._paged("/places", params)

    async def right_specs(self) -> list[dict[str, Any]]:
        return await self._paged("/rights/specs")

    async def right_spec(self, spec_id: str) -> dict[str, Any] | None:
        body = await self._http.get(f"/rights/specs/{_segment(spec_id)}", allow_404=True)
        return None if body is None else _require_dict(body, "APDS right specification")

    async def assigned_rights(self, spec_ids: list[str], credential: str, credential_types: str) -> list[dict[str, Any]]:
        params = {"right_spec": ",".join(spec_ids), "credential_id": credential, "credential_type": credential_types}
        return await self._paged("/rights/assigned", params)
