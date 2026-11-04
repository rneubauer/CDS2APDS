"""Runs every curl example in docs/api/README.md against the service, so the examples can't rot.

Each ```sh block starts with `# -> <status>` and holds one curl command. The command is parsed
(method, URL, -H headers, -d body) and sent to the app, which runs on the in-memory fake upstream.
"""
from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from cds_apds_link import Settings, create_app
from fake_upstream import CONFORMANCE, REPO, FakeUpstream, load_json

README = REPO / "docs" / "api" / "README.md"
FIXTURES = load_json(CONFORMANCE / "fixtures.json")
EXAMPLE_BASE = "http://localhost:8080"
EXAMPLE_TOKEN = "example-token"
BLOCK_RE = re.compile(r"```sh\n# -> (\d{3})\n(.*?)```", re.DOTALL)


@dataclass(frozen=True)
class CurlExample:
    status: int
    method: str
    path: str
    headers: dict[str, str] = field(default_factory=dict)
    body: object = None


def parse_curl(command: str, status: int) -> CurlExample:
    args = shlex.split(command.replace("\\\n", " "))
    assert args and args[0] == "curl", f"not a curl command: {command!r}"
    method, url, headers, data = "GET", None, {}, None
    rest = iter(args[1:])
    for arg in rest:
        if arg == "-s":
            continue
        if arg == "-X":
            method = next(rest)
        elif arg == "-H":
            name, _, value = next(rest).partition(":")
            headers[name.strip()] = value.strip()
        elif arg == "-d":
            data = next(rest)
            method = "POST" if method == "GET" else method
        elif arg.startswith("http"):
            url = arg
        else:
            raise AssertionError(f"unsupported curl option {arg!r}; extend parse_curl")
    assert url and url.startswith(EXAMPLE_BASE), f"examples must use {EXAMPLE_BASE}: {url!r}"
    parts = urlsplit(url)
    path = parts.path + (f"?{parts.query}" if parts.query else "")
    return CurlExample(status, method, path, headers, json.loads(data) if data is not None else None)


def load_examples() -> list[CurlExample]:
    text = README.read_text(encoding="utf-8")
    return [parse_curl(block.strip(), int(status)) for status, block in BLOCK_RE.findall(text)]


EXAMPLES = load_examples()


def test_readme_has_an_example_for_every_route() -> None:
    settings = Settings.from_env(FIXTURES["config"])
    routes = {(m, r.path) for r in create_app(settings).routes if r.path.startswith("/") and hasattr(r, "methods")
              for m in r.methods if not r.path.startswith(("/docs", "/redoc", "/openapi"))}
    covered = {(e.method, re.sub(r"/zones/[^/]+/", "/zones/{zone_id}/", urlsplit(e.path).path)) for e in EXAMPLES}
    missing = {r for r in routes if r[0] != "HEAD"} - covered
    assert not missing, f"docs/api/README.md has no curl example for {sorted(missing)}"


@pytest.mark.parametrize("example", EXAMPLES, ids=[f"{e.method} {e.path}" for e in EXAMPLES])
def test_readme_example(example: CurlExample) -> None:
    settings = Settings.from_env({**FIXTURES["config"], "LINK_WEBHOOK_TOKEN": EXAMPLE_TOKEN})
    upstream = FakeUpstream(FIXTURES)
    with TestClient(create_app(settings, transport=upstream.transport())) as client:
        resp = client.request(example.method, example.path, headers=example.headers, json=example.body)
    assert resp.status_code == example.status, resp.text
    envelope = resp.json()
    assert envelope["success"] is (example.status < 400), envelope


def test_parse_curl_reads_method_headers_and_body() -> None:
    example = parse_curl(
        "curl -s -X POST http://localhost:8080/x?a=1 \\\n  -H 'A: b' \\\n  -d '{\"k\": 1}'", 200,
    )
    assert example == CurlExample(200, "POST", "/x?a=1", {"A": "b"}, {"k": 1})
    with pytest.raises(AssertionError):
        parse_curl("curl --unknown http://localhost:8080/", 200)
