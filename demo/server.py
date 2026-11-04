"""Offline "Civic District" demo of the CDS-APDS link service.

Runs the Python reference link service unchanged, wired to the same in-memory CDS and APDS
upstream that the conformance tests use (services/python/tests/fake_upstream.py, driven by
conformance/fixtures.json and examples/). It adds only:

- GET /demo/               the demo page (demo/static)
- GET /demo/upstream.json  the fictional upstream records the page needs to draw its map
                           (zone and area geometry, place points). Assigned rights are left
                           out, so no credential is ever sent to the browser.

All link-service API routes (/health, /sync, /links, /issues, /zones/..., /permits/verify,
/webhooks/apds) are served exactly as the service defines them. No network access is needed.

    pip install -e services/python
    python demo/server.py            # http://127.0.0.1:8742/demo/
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from types import ModuleType
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from cds_apds_link import Settings, create_app

DEMO_DIR = Path(__file__).resolve().parent
REPO = DEMO_DIR.parent
STATIC_DIR = DEMO_DIR / "static"
FAKE_UPSTREAM_PATH = REPO / "services" / "python" / "tests" / "fake_upstream.py"
DEFAULT_PORT = 8742


def _load_fake_upstream() -> ModuleType:
    """Import the test suite's fake upstream by path, so the demo and the tests share one copy."""
    spec = importlib.util.spec_from_file_location("cds2apds_demo_fake_upstream", FAKE_UPSTREAM_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {FAKE_UPSTREAM_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _map_data(upstream: Any) -> dict[str, Any]:
    """Upstream records the page draws. Deliberately excludes assigned rights (credentials)."""
    return {
        "cds": {"zones": upstream.zones, "areas": upstream.areas, "policies": upstream.policies},
        "apds": {"elements": upstream.elements, "right_specs": upstream.specs},
    }


def build_demo_app() -> FastAPI:
    fake = _load_fake_upstream()
    fixtures = fake.load_json(fake.CONFORMANCE / "fixtures.json")
    settings = Settings.from_env({**fixtures["config"], "HOST": "127.0.0.1"})
    upstream = fake.FakeUpstream(fixtures)
    app = create_app(settings, transport=upstream.transport())

    service_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        async with service_lifespan(application) as state:
            await application.state.service.sync()  # same work as POST /sync, before any request
            yield state

    app.router.lifespan_context = lifespan
    map_data = _map_data(upstream)

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse("/demo/")

    @app.get("/demo/upstream.json", include_in_schema=False)
    async def upstream_json() -> JSONResponse:
        return JSONResponse(map_data)

    app.mount("/demo", StaticFiles(directory=STATIC_DIR, html=True), name="demo")
    return app


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Offline Civic District demo of the CDS-APDS link service")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"port on 127.0.0.1 (default {DEFAULT_PORT})")
    args = parser.parse_args(argv)

    import uvicorn

    print(f"Civic District demo: http://127.0.0.1:{args.port}/demo/  (Ctrl+C to stop)", flush=True)
    uvicorn.run(build_demo_app(), host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
