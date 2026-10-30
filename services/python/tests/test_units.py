"""Unit tests for behaviour the shared conformance fixtures do not exercise."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from cds_apds_link import Settings, create_app
from cds_apds_link.geo import centroid, point_of, round_half_up
from cds_apds_link import registry as registry_module
from cds_apds_link.offstreet import availability, linked_place_ids, multilingual
from cds_apds_link.permits import decide, evaluate, mask_credential, parse_instant, programme_active, programmes
from cds_apds_link.registry import ApdsSnapshot, CdsSnapshot, Link, Ref, Registry, build_links, parse_apds_reference
from fake_upstream import CONFORMANCE, FakeUpstream, load_json

AT = datetime(2026, 6, 1, tzinfo=timezone.utc)
APDS = "https://apds.example.org/v4"


def ext(url: str, ids: list[str] | None = None, name: str = "APDS") -> dict:
    ref = {"name": name, "reference_url": url}
    if ids is not None:
        ref["ids"] = ids
    return ref


# --- config ---------------------------------------------------------------

def test_settings_validation() -> None:
    with pytest.raises(ValueError, match="CDS_BASE_URL is required"):
        Settings.from_env({"APDS_BASE_URL": APDS})
    with pytest.raises(ValueError, match="absolute"):
        Settings.from_env({"CDS_BASE_URL": "cds.example.org", "APDS_BASE_URL": APDS})
    with pytest.raises(ValueError, match="between"):
        Settings.from_env({"CDS_BASE_URL": "https://c", "APDS_BASE_URL": APDS, "DEFAULT_RADIUS_M": "9000"})
    with pytest.raises(ValueError, match="integer"):
        Settings.from_env({"CDS_BASE_URL": "https://c", "APDS_BASE_URL": APDS, "PORT": "x"})
    with pytest.raises(ValueError, match="one of"):
        Settings.from_env({"CDS_BASE_URL": "https://c", "APDS_BASE_URL": APDS, "APDS_AUTH_SCHEME": "basic"})
    s = Settings.from_env({"CDS_BASE_URL": "https://c/", "APDS_BASE_URL": APDS + "/", "APDS_AUTH_SCHEME": "MCC"})
    assert (s.cds_base_url, s.apds_base_url, s.apds_auth_scheme, s.port) == ("https://c", APDS, "mcc", 8080)


# --- references and registry ---------------------------------------------

def test_parse_apds_reference_variants() -> None:
    assert parse_apds_reference(ext(f"{APDS}/places/p1")) == ("places", "p1")
    assert parse_apds_reference(ext(f"{APDS}/places/p1", ["p2"])) == ("places", "p2")
    assert parse_apds_reference(ext(f"{APDS}/rights/specs/r1")) == ("rights/specs", "r1")
    assert parse_apds_reference(ext(f"{APDS}/places/p1", name="apds")) == ("places", "p1")
    assert parse_apds_reference(ext(f"{APDS}/places")) == ("", "")
    assert parse_apds_reference(ext(f"{APDS}/sessions/s1")) == ("", "")
    assert parse_apds_reference(ext(f"{APDS}/places/p1", name="WZDx")) is None
    assert parse_apds_reference("not a dict") is None


def test_stale_zone_reference_is_repointed() -> None:
    cds = CdsSnapshot(zones=[{"curb_zone_id": "z-new", "prev_curb_zone_ids": ["z-old"]}])
    apds = ApdsSnapshot.from_lists(
        [{"id": "va1", "type": "vehicularAccess", "operatorDefinedReference": {"id": "z-old", "version": 1, "className": "CdsCurbZone"}}], []
    )
    links, issues = build_links(cds, apds)
    assert [(l.kind, l.status, l.cds.id) for l in links] == [("access", "apds_only", "z-new")]
    assert [i.code for i in issues] == ["stale_cds_reference"]


def test_missing_and_invalid_references_are_reported() -> None:
    cds = CdsSnapshot(
        zones=[{"curb_zone_id": "z1", "external_references": [ext(f"{APDS}/rights/specs/r1"), ext(f"{APDS}/bogus")]}],
        policies=[{"curb_policy_id": "p1", "external_references": [ext(f"{APDS}/places/pl1"), ext(f"{APDS}/rights/specs/missing")]}],
    )
    apds = ApdsSnapshot.from_lists(
        [{"id": "pl1", "type": "place", "operatorDefinedReference": {"id": "gone", "version": 1, "className": "CdsCurbArea"}},
         {"id": "pl2", "type": "place", "operatorDefinedReference": {"id": "x", "version": 1, "className": "SomethingElse"}}],
        [],
    )
    links, issues = build_links(cds, apds)
    assert [(l.kind, l.status, l.apds.id) for l in links] == [("permit", "cds_only", "missing")]
    assert sorted(i.code for i in issues) == [
        "apds_target_missing", "cds_target_missing", "invalid_reference", "invalid_reference", "invalid_reference",
    ]


# --- geometry and availability -------------------------------------------

def test_geometry_helpers() -> None:
    assert centroid({"type": "LineString", "coordinates": [[0, 0], [2, 2]]}) == (1.0, 1.0)
    assert centroid({"type": "Point", "coordinates": [3, 4]}) == (4.0, 3.0)
    for bad in (None, {"type": "Polygon", "coordinates": []}, {"type": "Circle"}, {"type": "LineString", "coordinates": [["a", 1]]}):
        with pytest.raises(ValueError):
            centroid(bad)
    assert point_of([{"type": "Polygon"}]) is None and point_of([]) is None
    assert round_half_up(2.5) == 3 and round_half_up(-0.5) == 0


def test_availability_rules() -> None:
    table = lambda rec: {"hierarchyElementReference": {"supply": [{"supplyViewType": "spaceView", "supplyQuantity": 10}], "demandTable": [{"demandType": rec}]}}  # noqa: E731
    assert availability(table([{"recordDateTime": "2026-01-01T00:00:00Z", "count": 12}])) == (10, 0, "2026-01-01T00:00:00Z")
    latest = table([{"recordDateTime": "2026-01-01T00:00:00Z", "count": 1}, {"recordDateTime": "2026-01-02T00:00:00Z", "count": 4}])
    assert availability(latest) == (10, 6, "2026-01-02T00:00:00Z")
    assert availability(table([{"recordDateTime": "2026-01-01T00:00:00Z", "percentage": 25}]))[1] == 8
    assert availability({"characteristics": {"spacesTotal": 5}}) == (5, None, None)
    assert multilingual([{"language": "fr", "string": "Parc"}]) == "Parc" and multilingual(None) is None


# --- permit evaluation ---------------------------------------------------

SPEC = {"validity": {"validityStatus": "definedByValidityTimeSpec", "validityTimeSpecification": {"overallStartTime": "2026-01-01T00:00:00Z"}}}


def test_programme_activity() -> None:
    assert programme_active(SPEC, AT)
    assert not programme_active(None, AT)
    assert not programme_active({"validity": {"validityStatus": "suspended", "validityTimeSpecification": {"overallStartTime": "2026-01-01T00:00:00Z"}}}, AT)
    assert not programme_active({"validity": {"validityTimeSpecification": {"overallStartTime": "2026-01-01T00:00:00Z", "overallEndTime": "2026-06-01T00:00:00Z"}}}, AT)
    assert evaluate({"id": "a"}, None, AT) == "programme_inactive"


def test_decide_prefers_valid_then_latest_expiry() -> None:
    r1 = {"id": "r1", "expiry": "2026-07-01T00:00:00Z"}
    r2 = {"id": "r2", "expiry": "2026-09-01T00:00:00Z"}
    r3 = {"id": "r3"}
    assert decide([]) == ("not_found", None)
    assert decide([(r1, "valid"), (r2, "valid")]) == ("valid", r2)
    assert decide([(r1, "valid"), (r3, "valid")]) == ("valid", r3)
    assert decide([(r1, "expired"), (r2, "programme_inactive")]) == ("programme_inactive", r2)


def test_credential_helpers() -> None:
    assert mask_credential("ABC") == "***"
    assert mask_credential("ABCDEFG") == "ABC***EFG"
    assert parse_instant("2026-01-01T00:00:00").tzinfo is not None
    with pytest.raises(ValueError):
        parse_instant("soon")


# --- HTTP edge cases -----------------------------------------------------

def _client(handler=None, **env) -> TestClient:
    fixtures = load_json(CONFORMANCE / "fixtures.json")
    settings = Settings.from_env({**fixtures["config"], **env})
    transport = httpx.MockTransport(handler) if handler else FakeUpstream(fixtures).transport()
    return TestClient(create_app(settings, transport=transport))


def test_upstream_failures_become_502() -> None:
    def broken(request: httpx.Request) -> httpx.Response:
        if "credential" in str(request.url):
            raise httpx.ConnectError("boom")
        return httpx.Response(500, json={})

    with _client(broken) as client:
        resp = client.post("/sync")
        assert resp.status_code == 502 and resp.json()["error"]["code"] == "upstream_error"
    with _client(lambda r: httpx.Response(200, text="not json")) as client:
        assert client.get("/links").json()["error"]["code"] == "upstream_error"
    with _client(lambda r: httpx.Response(200, json={"data": {"zones": "nope"}})) as client:
        assert client.post("/sync").status_code == 502


def test_upstream_auth_headers_and_no_credential_leak() -> None:
    fixtures = load_json(CONFORMANCE / "fixtures.json")
    upstream = FakeUpstream(fixtures)
    env = {**fixtures["config"], "CDS_TOKEN": "c-tok", "APDS_TOKEN": "a-tok", "APDS_AUTH_SCHEME": "mcc"}
    with TestClient(create_app(Settings.from_env(env), transport=upstream.transport())) as client:
        body = {"curb_zone_id": "3f2a9c1e-5b7d-4e8a-9c01-00000000b003", "credential": "ZA-004217"}
        resp = client.post("/permits/verify", json=body)
    assert resp.status_code == 200 and "ZA-004217" not in resp.text
    cds_req = next(r for r in upstream.requests if r.url.host == "cds.example.org")
    apds_req = next(r for r in upstream.requests if r.url.host == "apds.example.org")
    assert cds_req.headers["authorization"] == "Bearer c-tok"
    assert apds_req.headers["x-mcc-access-token"] == "a-tok" and "authorization" not in apds_req.headers


def test_credential_never_logged(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)  # root only; the service must keep httpx itself quiet
    with _client() as client:
        body = {"curb_zone_id": "3f2a9c1e-5b7d-4e8a-9c01-00000000b003", "credential": "ZA-004217"}
        assert client.post("/permits/verify", json=body).status_code == 200
    assert "ZA-004217" not in caplog.text
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING


def test_upstream_redirect_is_not_followed() -> None:
    def redirecting(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://evil.example/"}, json={"data": {}})

    with _client(redirecting) as client:
        resp = client.post("/sync")
    assert resp.status_code == 502 and resp.json()["error"]["code"] == "upstream_error"


def test_request_body_validation() -> None:
    with _client() as client:
        assert client.post("/permits/verify", content=b"{bad", headers={"content-type": "application/json"}).status_code == 400
        assert client.post("/permits/verify", json=[1]).status_code == 400
        assert client.post("/permits/verify", json={"curb_zone_id": "z", "credential": "x", "at": 5}).status_code == 400
        hdrs = {"X-APDS-Event-Type": "PlaceUpdated", "X-Link-Webhook-Token": "conformance-token"}
        assert client.post("/webhooks/apds", json={"version": 1}, headers=hdrs).status_code == 400


def test_webhook_right_specification_events() -> None:
    hdrs = {"X-Link-Webhook-Token": "conformance-token"}
    spec_id = "7d41e6b2-8c3f-4a9d-b210-00000000f101"
    with _client() as client:
        r = client.post("/webhooks/apds", json={"id": spec_id}, headers={**hdrs, "X-APDS-Event-Type": "RightSpecificationDeleted"})
        assert r.json()["data"]["applied"] is True
        assert client.get("/issues").json()["data"][0]["code"] == "apds_target_missing"
        client.post("/webhooks/apds", json={"id": spec_id, "version": 2}, headers={**hdrs, "X-APDS-Event-Type": "RightSpecificationUpdated"})
        assert client.get("/issues").json()["data"] == []


def test_webhook_without_token_configured_and_zone_with_bad_geometry() -> None:
    fake = FakeUpstream(load_json(CONFORMANCE / "fixtures.json"))

    def cds_bad_zone(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/curbs/zones/zbad":
            return httpx.Response(200, json={"data": {"curb_zone_id": "zbad", "geometry": {"type": "Circle"}}})
        return fake.handle(request)

    with _client(cds_bad_zone, LINK_WEBHOOK_TOKEN="") as client:
        r = client.post("/webhooks/apds", json={"id": "s"}, headers={"X-APDS-Event-Type": "RateUpdated"})
        assert r.status_code == 200 and r.json()["data"]["applied"] is False
        assert client.get("/zones/zbad/off-street").status_code == 502


# --- review regressions --------------------------------------------------

def test_unparseable_timestamps_fail_closed() -> None:
    assert evaluate({"id": "a", "expiry": "2028-01-01T00:00:00+0000"}, SPEC, AT) == "expired"
    assert evaluate({"id": "a", "issuanceTime": "garbage"}, SPEC, AT) == "not_yet_valid"
    bad_end = {"validity": {"validityTimeSpecification": {"overallStartTime": "2026-01-01T00:00:00Z", "overallEndTime": "soon"}}}
    assert not programme_active(bad_end, AT)
    for text in ("2026-06-01 12:00:00+00:00", "2026-06-01T12:00:00+0000", "20260601"):
        with pytest.raises(ValueError):
            parse_instant(text)


def test_reference_url_must_be_absolute_http() -> None:
    assert parse_apds_reference(ext("/places/p1")) == ("", "")
    assert parse_apds_reference(ext("ftp://apds.example.org/places/p1")) == ("", "")


def test_registry_refuses_new_ids_beyond_cap() -> None:
    reg = Registry(max_entries=1)
    assert reg.upsert_element({"id": "a"}) and reg.upsert_element({"id": "a", "version": 2})
    assert not reg.upsert_element({"id": "b"})
    assert reg.upsert_right_spec({"id": "s"}) and not reg.upsert_right_spec({"id": "t"})
    with _client() as client:
        client.post("/sync")
        client.app.state.service.registry.max_entries = 4
        hdrs = {"X-APDS-Event-Type": "PlaceCreated", "X-Link-Webhook-Token": "conformance-token"}
        resp = client.post("/webhooks/apds", json={"id": "new-place", "type": "place"}, headers=hdrs)
        assert resp.status_code == 400 and "full" in resp.json()["error"]["message"]


def test_zone_id_stays_one_path_segment_upstream() -> None:
    fixtures = load_json(CONFORMANCE / "fixtures.json")
    upstream = FakeUpstream(fixtures)
    with TestClient(create_app(Settings.from_env(fixtures["config"]), transport=upstream.transport())) as client:
        resp = client.post("/permits/verify", json={"curb_zone_id": "../policies/x?y=1", "credential": "ZA-004217"})
    assert resp.status_code == 404
    cds_paths = [r.url.raw_path for r in upstream.requests if r.url.host == "cds.example.org"]
    assert cds_paths == [b"/curbs/zones/..%2Fpolicies%2Fx%3Fy%3D1"]


def test_oversized_body_is_rejected() -> None:
    with _client() as client:
        big = {"curb_zone_id": "z", "credential": "x", "pad": "a" * 1_100_000}
        resp = client.post("/permits/verify", json=big)
        assert resp.status_code == 400 and "too large" in resp.json()["error"]["message"]


# --- malformed data and error envelopes (parity with the TypeScript service) ---

WEBHOOK = {"X-APDS-Event-Type": "PlaceCreated", "X-Link-Webhook-Token": "conformance-token"}


def test_unknown_routes_and_methods_use_the_envelope() -> None:
    with _client() as client:
        for method, path in (("GET", "/nope"), ("DELETE", "/health"), ("GET", "/sync"), ("GET", "/openapi.json"), ("GET", "/docs")):
            resp = client.request(method, path)
            assert resp.status_code == 404, f"{method} {path}"
            assert resp.json() == {"success": False, "data": None, "error": {"code": "not_found", "message": "route not found"}}


def test_unexpected_exception_is_an_opaque_500() -> None:
    with _client() as client:
        def explode(*_: object) -> list:
            raise RuntimeError("Bearer s3cret-token")

        client.app.state.service.registry.find = explode
        client.post("/sync")
        resp = client.get("/links")
    assert resp.status_code == 500
    assert resp.json() == {"success": False, "data": None, "error": {"code": "internal_error", "message": "internal error"}}
    assert "s3cret" not in resp.text


def test_framework_http_errors_map_like_fastify() -> None:
    from fastapi import HTTPException

    with _client() as client:
        def raise_status(status: int) -> None:
            raise HTTPException(status, "framework detail")

        client.app.add_api_route("/teapot", lambda: raise_status(418))
        client.app.add_api_route("/unavailable", lambda: raise_status(503))
        teapot, unavailable = client.get("/teapot"), client.get("/unavailable")
    assert teapot.status_code == 400 and teapot.json()["error"] == {"code": "invalid_request", "message": "invalid request"}
    assert unavailable.status_code == 500 and unavailable.json()["error"]["code"] == "internal_error"


def test_malformed_class_name_and_reference_url_do_not_crash() -> None:
    cds = CdsSnapshot(zones=[{"curb_zone_id": "z1", "external_references": [ext("http://[oops/places/x")]}])
    apds = ApdsSnapshot.from_lists([{"id": "p1", "operatorDefinedReference": {"id": "z1", "className": ["CdsCurbZone"]}}], [])
    links, issues = build_links(cds, apds)
    assert links == [] and [i.code for i in issues] == ["invalid_reference"]
    assert parse_apds_reference(ext("http://[oops/places/x")) == ("", "")


def test_non_list_and_unhashable_cds_fields_are_ignored() -> None:
    cds = CdsSnapshot(zones=[{"curb_zone_id": "z-new", "prev_curb_zone_ids": "z-old"}, {"curb_zone_id": ["odd"]}])
    apds = ApdsSnapshot.from_lists([{"id": "va1", "operatorDefinedReference": {"id": "z-old", "className": "CdsCurbZone"}}], [])
    links, issues = build_links(cds, apds)
    assert links == [] and [i.code for i in issues] == ["cds_target_missing"]


def test_permit_rules_only_match_list_members() -> None:
    ref = [ext(f"{APDS}/rights/specs/r1")]
    policy = lambda rule: {"curb_policy_id": "p", "rules": [rule], "external_references": ref}  # noqa: E731
    assert programmes([policy({"user_classes": "permit_holder"})]) == []
    assert programmes([policy({"user_classes": 5, "purposes": {"permit": 1}})]) == []
    assert [p.right_specification_id for p in programmes([policy({"purposes": ["permit"]})])] == ["r1"]


def test_string_id_lists_are_not_iterated_per_character() -> None:
    fake = FakeUpstream(load_json(CONFORMANCE / "fixtures.json"))

    def odd_zone(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/curbs/zones/zs":
            return httpx.Response(200, json={"data": {"curb_zone_id": "zs", "curb_policy_ids": "pq"}})
        return fake.handle(request)

    with _client(odd_zone) as client:
        resp = client.post("/permits/verify", json={"curb_zone_id": "zs", "credential": "ZA-004217"})
    assert resp.status_code == 200 and resp.json()["data"]["result"] == "no_programme"
    assert not any(r.url.path.startswith("/curbs/policies/") for r in fake.requests)
    link = Link("supply", "cds_only", Ref("CurbArea", "a"), Ref("place", "p1"))
    elements = {"p1": {"id": "p1", "type": "place"}}
    assert linked_place_ids({"curb_zone_id": "z", "curb_area_ids": "abc"}, [link], elements) == set()
    assert linked_place_ids({"curb_zone_id": "z", "curb_area_ids": [{"x": 1}, "a"]}, [link], elements) == {"p1"}


def test_malformed_webhook_does_not_poison_the_registry() -> None:
    with _client() as client:
        bad = {"id": "p-bad", "type": "place", "operatorDefinedReference": {"id": "z", "className": ["CdsCurbZone"]}}
        assert client.post("/webhooks/apds", json=bad, headers=WEBHOOK).status_code == 200
        assert client.get("/links").status_code == 200
        assert client.post("/webhooks/apds", json={"id": "p-ok", "type": "place"}, headers=WEBHOOK).status_code == 200


def test_registry_update_is_atomic(monkeypatch: pytest.MonkeyPatch) -> None:
    reg = Registry()
    reg.upsert_element({"id": "a"})
    before = (reg.apds, reg.links, reg.issues)

    def broken(*_: object) -> None:
        raise RuntimeError("rebuild failed")

    monkeypatch.setattr(registry_module, "build_links", broken)
    with pytest.raises(RuntimeError):
        reg.upsert_element({"id": "b"})
    assert (reg.apds, reg.links, reg.issues) == before and "b" not in reg.apds.elements


def test_booleans_are_not_numbers() -> None:
    supply = lambda qty, rec: {"hierarchyElementReference": {"supply": [{"supplyViewType": "spaceView", "supplyQuantity": qty}], "demandTable": [{"demandType": rec}]}}  # noqa: E731
    assert availability(supply(True, [])) == (None, None, None)
    assert availability(supply(10, [{"recordDateTime": "2026-01-01T00:00:00Z", "count": True}]))[1] is None
    assert availability(supply(10, [{"recordDateTime": "2026-01-01T00:00:00Z", "percentage": False}]))[1] is None
    assert availability({"characteristics": {"spacesTotal": True}}) == (None, None, None)
    with pytest.raises(ValueError):
        centroid({"type": "Point", "coordinates": [True, 1]})
    assert point_of([{"type": "Point", "coordinates": [1, False]}]) is None


def test_mixed_offset_demand_records_do_not_crash() -> None:
    rec = [{"recordDateTime": "2026-01-01T00:00:00Z", "count": 1}, {"recordDateTime": "2026-01-02T00:00:00", "count": 2}]
    element = {"characteristics": {"spacesTotal": 10}, "hierarchyElementReference": {"demandTable": [{"demandType": rec}]}}
    assert availability(element) == (10, 8, "2026-01-02T00:00:00")


def test_non_standard_json_constants_from_upstream_are_rejected() -> None:
    fake = FakeUpstream(load_json(CONFORMANCE / "fixtures.json"))

    def nan_zones(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/curbs/zones":
            return httpx.Response(200, content=b'{"data": {"zones": [{"curb_zone_id": "z", "x": NaN}]}}')
        return fake.handle(request)

    with _client(nan_zones) as client:
        resp = client.post("/sync")
    assert resp.status_code == 502 and resp.json()["error"]["code"] == "upstream_error"


def test_zone_without_id_does_not_crash_off_street() -> None:
    fake = FakeUpstream(load_json(CONFORMANCE / "fixtures.json"))

    def anonymous_zone(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/curbs/zones/zx":
            return httpx.Response(200, json={"data": {"geometry": {"type": "Point", "coordinates": [0, 0]}}})
        return fake.handle(request)

    with _client(anonymous_zone) as client:
        resp = client.get("/zones/zx/off-street")
    assert resp.status_code == 200 and resp.json()["data"]["curb_zone_id"] is None
