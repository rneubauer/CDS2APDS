"""Smoke test for the offline demo: the page is served and every API call it makes succeeds.

Run from the repository root:  pytest demo
"""
from __future__ import annotations

import importlib.util
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

DEMO_DIR = Path(__file__).resolve().parent
STATIC = DEMO_DIR / "static"
ZONES = {
    "apron": "3f2a9c1e-5b7d-4e8a-9c01-00000000b001",
    "metered": "3f2a9c1e-5b7d-4e8a-9c01-00000000b002",
    "permit": "3f2a9c1e-5b7d-4e8a-9c01-00000000b003",
}
FIXED_AT = "2026-06-01T12:00:00Z"
# The preset chips on the page: (credential, credential_type, at).
PRESETS = [
    ("ZA-004217", "", ""),
    ("ZA-999999", "", ""),
    ("EXM1234", "licensePlate", ""),
    ("ZA-004217", "", "2027-02-01T00:00:00Z"),
]


def _load_server():
    spec = importlib.util.spec_from_file_location("cds2apds_demo_server", DEMO_DIR / "server.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(_load_server().build_demo_app()) as test_client:
        yield test_client


def _ok(resp) -> object:
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True and body["error"] is None, body
    return body["data"]


def test_registry_is_synced_on_startup(client: TestClient) -> None:
    data = _ok(client.get("/health"))
    assert data["last_sync"] is not None
    assert data["links"] == 3


def test_page_and_assets_are_served(client: TestClient) -> None:
    page = client.get("/demo/")
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    assert 'id="map"' in page.text
    for asset, kind in (("demo.js", "javascript"), ("demo.css", "text/css")):
        resp = client.get(f"/demo/{asset}")
        assert resp.status_code == 200 and kind in resp.headers["content-type"]
    assert client.get("/", follow_redirects=False).headers["location"] == "/demo/"


def test_page_loads_nothing_from_the_network() -> None:
    for path in STATIC.iterdir():
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"""(src|href)\s*=\s*["']https?:""", text), path.name
        assert "@import" not in text and "url(http" not in text, path.name
        assert not re.search(r"""fetch\(\s*["'`]https?:""", text), path.name


def test_upstream_json_has_map_data_but_no_credentials(client: TestClient) -> None:
    resp = client.get("/demo/upstream.json")
    assert resp.status_code == 200
    data = resp.json()
    assert {z["curb_zone_id"] for z in data["cds"]["zones"]} == set(ZONES.values())
    assert all("geometry" in z for z in data["cds"]["zones"])
    assert any(e.get("indicativePointLocation") for e in data["apds"]["elements"])
    assert "ZA-004217" not in resp.text and "EXM1234" not in resp.text


def test_registry_panel_calls(client: TestClient) -> None:
    links = _ok(client.get("/links"))
    assert {link["kind"] for link in links} == {"access", "supply", "permit"}
    assert _ok(client.get("/issues")) == []
    synced = _ok(client.post("/sync"))
    assert len(synced["links"]) == 3


@pytest.mark.parametrize("zone", ZONES.values())
def test_t1_links_per_zone(client: TestClient, zone: str) -> None:
    links = _ok(client.get("/links", params={"cds_id": zone}))
    kinds = [link["kind"] for link in links]
    assert kinds == (["access"] if zone == ZONES["apron"] else [])


@pytest.mark.parametrize("radius", ["100", "400", "2000"])
@pytest.mark.parametrize("zone", ZONES.values())
def test_t2_off_street_per_zone_and_radius(client: TestClient, zone: str, radius: str) -> None:
    data = _ok(client.get(f"/zones/{zone}/off-street", params={"radius_m": radius}))
    assert data["places"], "every zone should at least show the linked Civic Garage"
    assert data["places"][0]["name"] == "Civic Garage" and data["places"][0]["linked"] is True


@pytest.mark.parametrize("credential,credential_type,at", PRESETS)
@pytest.mark.parametrize("zone", ZONES.values())
def test_t3_presets_succeed_on_every_zone(client: TestClient, zone: str, credential: str, credential_type: str, at: str) -> None:
    body = {"curb_zone_id": zone, "credential": credential}
    if credential_type:
        body["credential_type"] = credential_type
    if at:
        body["at"] = at
    data = _ok(client.post("/permits/verify", json=body))
    assert credential not in str(data), "the credential must come back masked"


@pytest.mark.parametrize("credential,credential_type,expected", [
    ("ZA-004217", "", "valid"),
    ("ZA-999999", "", "not_found"),
    ("EXM1234", "licensePlate", "valid"),
])
def test_t3_talk_track_outcomes(client: TestClient, credential: str, credential_type: str, expected: str) -> None:
    body = {"curb_zone_id": ZONES["permit"], "credential": credential, "at": FIXED_AT}
    if credential_type:
        body["credential_type"] = credential_type
    assert _ok(client.post("/permits/verify", json=body))["result"] == expected
    expired = {"curb_zone_id": ZONES["permit"], "credential": "ZA-004217", "at": "2027-02-01T00:00:00Z"}
    assert _ok(client.post("/permits/verify", json=expired))["result"] == "expired"
    no_programme = {"curb_zone_id": ZONES["metered"], "credential": "ZA-004217", "at": FIXED_AT}
    assert _ok(client.post("/permits/verify", json=no_programme))["result"] == "no_programme"
