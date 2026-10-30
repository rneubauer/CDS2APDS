"""HTTP API of the link service (docs/03-link-service.md §3.4)."""
from __future__ import annotations

import asyncio
import hmac
import json
import logging
import re
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from . import permits
from .config import Settings
from .errors import ServiceError, invalid_request, not_found, unauthorized, upstream_error
from .geo import centroid
from .jsonutil import as_list
from .offstreet import build_summary
from .registry import LINK_KINDS, ApdsSnapshot, CdsSnapshot, Registry
from .upstream import ApdsClient, CdsClient

log = logging.getLogger("cds_apds_link")

APDS_EVENT_TYPES = frozenset(
    f"{entity}{action}"
    for entity in ("AssignedRight", "Session", "Place", "RightSpecification", "Rate", "Organisation")
    for action in ("Created", "Updated", "Deleted")
)
RADIUS_RE = re.compile(r"^[0-9]{1,4}$")
MAX_BODY_BYTES = 1_048_576  # matches Fastify's default bodyLimit in the TypeScript service


def ok(data: Any) -> JSONResponse:
    return JSONResponse({"success": True, "data": data, "error": None})


def fail(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"success": False, "data": None, "error": {"code": code, "message": message}}, status_code=status)


class LinkService:
    def __init__(self, settings: Settings, client: httpx.AsyncClient, clock: Callable[[], datetime]) -> None:
        self.settings = settings
        self.cds = CdsClient(client, settings)
        self.apds = ApdsClient(client, settings)
        self.registry = Registry()
        self.clock = clock
        self._lock = asyncio.Lock()

    async def sync(self) -> None:
        async with self._lock:
            zones, areas, objects, policies, elements, specs = await asyncio.gather(
                self.cds.zones(), self.cds.areas(), self.cds.objects(), self.cds.policies(),
                self.apds.elements(), self.apds.right_specs(),
            )
            self.registry.replace(
                CdsSnapshot(zones, areas, objects, policies),
                ApdsSnapshot.from_lists(elements, specs),
                permits.format_instant(self.clock()),
            )
            log.info("sync complete: %d links, %d issues", len(self.registry.links), len(self.registry.issues))

    async def ensure_synced(self) -> None:
        if not self.registry.synced:
            await self.sync()

    async def zone(self, zone_id: str) -> dict[str, Any]:
        zone = await self.cds.zone(zone_id)
        if zone is None:
            raise not_found(f"curb zone {zone_id} not found")
        return zone

    async def off_street(self, zone_id: str, radius_m: int) -> dict[str, Any]:
        await self.ensure_synced()
        zone = await self.zone(zone_id)
        try:
            origin = centroid(zone.get("geometry"))
        except ValueError as exc:
            raise upstream_error(f"curb zone {zone_id} has unusable geometry: {exc}") from None
        nearby = await self.apds.places_near(origin[0], origin[1], radius_m)
        reg = self.registry
        return build_summary(zone, origin, radius_m, nearby, reg.apds.elements, reg.links, self.settings.apds_base_url)

    async def verify_permit(self, zone_id: str, credential: str, credential_type: str | None, at: datetime) -> dict[str, Any]:
        zone = await self.zone(zone_id)
        policy_ids = [p for p in as_list(zone.get("curb_policy_ids")) if isinstance(p, str)]
        policies = [p for p in await asyncio.gather(*(self.cds.policy(pid) for pid in policy_ids)) if p is not None]
        progs = permits.programmes(policies)
        base = {
            "curb_zone_id": zone_id,
            "at": permits.format_instant(at),
            "programmes": [p.to_json() for p in progs],
            "credential_masked": permits.mask_credential(credential),
        }
        if not progs:
            return {**base, "result": "no_programme", "assigned_right": None}
        spec_ids = sorted({p.right_specification_id for p in progs})
        rights = await self.apds.assigned_rights(spec_ids, credential, credential_type or "permit,licensePlate")
        candidates = [
            r for r in rights
            if isinstance(r.get("rightSpecification"), dict)
            and r["rightSpecification"].get("id") in spec_ids
            and permits.holds_credential(r, credential)
        ]
        needed = sorted({r["rightSpecification"]["id"] for r in candidates})
        specs = dict(zip(needed, await asyncio.gather(*(self.apds.right_spec(s) for s in needed))))
        outcomes = [(r, permits.evaluate(r, specs.get(r["rightSpecification"]["id"]), at)) for r in candidates]
        result, right = permits.decide(outcomes)
        return {**base, "result": result, "assigned_right": permits.right_summary(right)}

    async def apply_webhook(self, event_type: str, body: dict[str, Any]) -> bool:
        await self.ensure_synced()
        entity, action = _split_event(event_type)
        reg = self.registry
        if entity == "Place":
            if action == "Deleted":
                reg.remove_element(body["id"])
            elif not reg.upsert_element(body):
                raise invalid_request("registry is full; new APDS elements are refused")
            return True
        if entity == "RightSpecification":
            if action == "Deleted":
                reg.remove_right_spec(body["id"])
            elif not reg.upsert_right_spec(body):
                raise invalid_request("registry is full; new right specifications are refused")
            return True
        return False


def _split_event(event_type: str) -> tuple[str, str]:
    for action in ("Created", "Updated", "Deleted"):
        if event_type.endswith(action):
            return event_type[: -len(action)], action
    return event_type, ""


def _parse_radius(raw: str | None, default: int) -> int:
    if raw is None:
        return default
    if not RADIUS_RE.match(raw) or not 1 <= int(raw) <= 5000:
        raise invalid_request("radius_m must be an integer from 1 to 5000")
    return int(raw)


async def _json_object(request: Request) -> dict[str, Any]:
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise invalid_request("request body is too large")
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            raise invalid_request("request body is too large")
        chunks.append(chunk)
    try:
        body = json.loads(b"".join(chunks))
    except ValueError:
        raise invalid_request("request body must be JSON") from None
    if not isinstance(body, dict):
        raise invalid_request("request body must be a JSON object")
    return body


def _permit_request(body: dict[str, Any], clock: Callable[[], datetime]) -> tuple[str, str, str | None, datetime]:
    zone_id, credential = body.get("curb_zone_id"), body.get("credential")
    if not isinstance(zone_id, str) or not zone_id.strip():
        raise invalid_request("curb_zone_id is required")
    if not isinstance(credential, str) or not credential.strip():
        raise invalid_request("credential is required")
    credential_type = body.get("credential_type")
    if credential_type is not None and credential_type not in permits.CREDENTIAL_TYPES:
        raise invalid_request("credential_type must be 'permit' or 'licensePlate'")
    at_raw = body.get("at")
    if at_raw is None:
        return zone_id.strip(), permits.normalize_credential(credential), credential_type, clock()
    if not isinstance(at_raw, str):
        raise invalid_request("at must be an ISO-8601 instant")
    try:
        at = permits.parse_instant(at_raw)
    except ValueError:
        raise invalid_request("at must be an ISO-8601 instant") from None
    return zone_id.strip(), permits.normalize_credential(credential), credential_type, at


def _check_webhook_token(request: Request, expected: str | None) -> None:
    if not expected:
        return
    presented = request.headers.get("x-link-webhook-token", "")
    if not hmac.compare_digest(presented.encode(), expected.encode()):
        raise unauthorized("missing or invalid webhook token")


class CatchAllErrors:
    """Turn any uncaught exception into the 500 envelope (docs/03 §3.2).

    Only the exception's type is logged: its text could contain upstream credentials. Unlike a
    Starlette ``Exception`` handler this does not re-raise, so the server does not log a traceback.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def tracked_send(message: Message) -> None:
            nonlocal started
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, receive, tracked_send)
        except Exception as exc:
            if started:
                raise
            log.error("unexpected error: %s", type(exc).__name__)
            await fail(500, "internal_error", "internal error")(scope, receive, send)


def create_app(
    settings: Settings,
    transport: httpx.AsyncBaseTransport | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> FastAPI:
    client = httpx.AsyncClient(timeout=settings.http_timeout_ms / 1000, transport=transport)
    service = LinkService(settings, client, clock)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        await client.aclose()

    # No generated docs routes: every response, including unknown paths, is the JSON envelope.
    app = FastAPI(
        title="CDS-APDS link service", version="0.1.0", lifespan=lifespan,
        docs_url=None, redoc_url=None, openapi_url=None,
    )
    app.state.service = service
    app.add_middleware(CatchAllErrors)

    @app.exception_handler(ServiceError)
    async def _service_error(_: Request, exc: ServiceError) -> JSONResponse:
        if exc.status >= 500:
            log.warning("upstream failure: %s", exc.message)
        return fail(exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, __: RequestValidationError) -> JSONResponse:
        return fail(400, "invalid_request", "invalid request")

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        # Fastify answers an unknown path and a wrong method alike with its not-found handler.
        if exc.status_code in (404, 405):
            return fail(404, "not_found", "route not found")
        if 400 <= exc.status_code < 500:
            return fail(400, "invalid_request", "invalid request")
        log.error("unexpected error: HTTP %d", exc.status_code)
        return fail(500, "internal_error", "internal error")

    @app.get("/health")
    async def health() -> JSONResponse:
        reg = service.registry
        return ok({"status": "ok", "links": len(reg.links), "last_sync": reg.last_sync})

    @app.post("/sync")
    async def sync() -> JSONResponse:
        await service.sync()
        reg = service.registry
        return ok({"links": [l.to_json() for l in reg.links], "issues": [i.to_json() for i in reg.issues], "synced_at": reg.last_sync})

    @app.get("/links")
    async def links(cds_id: str | None = None, apds_id: str | None = None, kind: str | None = None) -> JSONResponse:
        if kind is not None and kind not in LINK_KINDS:
            raise invalid_request(f"kind must be one of {', '.join(LINK_KINDS)}")
        await service.ensure_synced()
        return ok([l.to_json() for l in service.registry.find(cds_id, apds_id, kind)])

    @app.get("/issues")
    async def issues() -> JSONResponse:
        await service.ensure_synced()
        return ok([i.to_json() for i in service.registry.issues])

    @app.get("/zones/{zone_id}/off-street")
    async def off_street(zone_id: str, request: Request) -> JSONResponse:
        radius = _parse_radius(request.query_params.get("radius_m"), settings.default_radius_m)
        return ok(await service.off_street(zone_id, radius))

    @app.post("/permits/verify")
    async def verify(request: Request) -> JSONResponse:
        zone_id, credential, credential_type, at = _permit_request(await _json_object(request), clock)
        return ok(await service.verify_permit(zone_id, credential, credential_type, at))

    @app.post("/webhooks/apds")
    async def webhook(request: Request) -> JSONResponse:
        _check_webhook_token(request, settings.webhook_token)
        event_type = request.headers.get("x-apds-event-type", "")
        if event_type not in APDS_EVENT_TYPES:
            raise invalid_request("X-APDS-Event-Type header is missing or not an APDS EventTypeEnum value")
        body = await _json_object(request)
        if not isinstance(body.get("id"), str) or not body["id"]:
            raise invalid_request("event data must include an id")
        applied = await service.apply_webhook(event_type, body)
        return ok({"event_type": event_type, "applied": applied})

    return app
