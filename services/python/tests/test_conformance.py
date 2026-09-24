"""Runs the shared conformance suite (conformance/cases.json) against the Python service."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from cds_apds_link import Settings, create_app
from fake_upstream import CONFORMANCE, FakeUpstream, load_json

FIXTURES = load_json(CONFORMANCE / "fixtures.json")
CASES = load_json(CONFORMANCE / "cases.json")
FIXED_NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def subset_match(expected: Any, actual: Any, path: str = "$") -> list[str]:
    if expected == "<any>":
        return []
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [f"{path}: expected object, got {actual!r}"]
        errors = []
        for key, value in expected.items():
            if key not in actual:
                errors.append(f"{path}.{key}: missing")
            else:
                errors += subset_match(value, actual[key], f"{path}.{key}")
        return errors
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            return [f"{path}: expected list of {len(expected)}, got {actual!r}"]
        return [e for i, (x, y) in enumerate(zip(expected, actual)) for e in subset_match(x, y, f"{path}[{i}]")]
    return [] if expected == actual else [f"{path}: expected {expected!r}, got {actual!r}"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_conformance(case: dict[str, Any]) -> None:
    settings = Settings.from_env(FIXTURES["config"])
    upstream = FakeUpstream(FIXTURES)
    with TestClient(create_app(settings, transport=upstream.transport(), clock=lambda: FIXED_NOW)) as client:
        for index, step in enumerate(case["steps"]):
            req = step["request"]
            resp = client.request(req["method"], req["path"], json=req.get("body"), headers=req.get("headers", {}))
            label = f"step {index}: {req['method']} {req['path']}"
            assert resp.status_code == step["expect"]["status"], f"{label}: {resp.text}"
            errors = subset_match(step["expect"]["body"], resp.json())
            assert not errors, f"{label}:\n" + "\n".join(errors)


def test_subset_match_reports_mismatches() -> None:
    assert subset_match({"a": [1, {"b": 2}]}, {"a": [1, {"b": 2, "c": 3}], "z": 0}) == []
    assert subset_match({"a": 1}, {}) == ["$.a: missing"]
    assert subset_match([1], [1, 2]) != []
    assert subset_match({"a": "<any>"}, {"a": None}) == []
