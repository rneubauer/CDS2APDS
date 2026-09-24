"""Validate every example payload against the vendored CDS 1.1 / APDS 4.1 schemas.

Usage:  python tools/validate_examples.py
Exit code is non-zero if any example fails validation.

Known upstream schema defects are patched in memory (never on disk) and are
reported on every run, so they stay visible until fixed upstream.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

ROOT = Path(__file__).resolve().parent.parent
CDS_MODELS = ROOT / "vendor" / "cds-1.1" / "Shared Data Models"
APDS_FILE = ROOT / "vendor" / "apds-4.1" / "apds-api-4.1.yaml"
EXAMPLES = ROOT / "examples"

# Upstream defects in APDS 4.1 that make valid payloads impossible.
APDS_PATCHES = {
    "Reference": (
        "requires both 'id' and 'className' but sets maxProperties: 1, so no "
        "instance can validate; minProperties/maxProperties removed",
        lambda s: {k: v for k, v in s.items() if k not in ("minProperties", "maxProperties")},
    ),
}



def _rfc7946_polygon(schema: dict) -> dict:
    props = {**schema["properties"], "coordinates": {"type": "array", "items": {"$ref": "./coordinates.yaml"}}}
    return {**schema, "properties": props}


# Upstream defects in the CDS 1.1 OpenAPI models (the CDS prose spec is correct).
CDS_PATCHES = {
    "geoJSON_polygon.yaml": (
        "Polygon 'coordinates' is modelled as a single list of positions (a LineString); "
        "RFC 7946 requires an array of linear rings; coordinates wrapped in an outer array",
        _rfc7946_polygon,
    ),
}


def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_cds_model(name: str) -> dict:
    schema = load_yaml(CDS_MODELS / name)
    if name in CDS_PATCHES:
        schema = CDS_PATCHES[name][1](schema)
    return schema


def cds_validator(schema_file: str) -> Draft202012Validator:
    def retrieve(uri: str) -> Resource:
        return Resource.from_contents(load_cds_model(uri.rsplit("/", 1)[-1]), default_specification=DRAFT202012)

    base = (CDS_MODELS / schema_file).as_uri()
    schema = {"$id": base, **load_cds_model(schema_file)}
    return Draft202012Validator(schema, registry=Registry(retrieve=retrieve))


def apds_components() -> dict:
    components = load_yaml(APDS_FILE)["components"]
    schemas = components["schemas"]
    for name, (_, patch) in APDS_PATCHES.items():
        schemas[name] = patch(schemas[name])
    return components


def apds_validator(schema_name: str, components: dict) -> Draft202012Validator:
    return Draft202012Validator({"components": components, "$ref": f"#/components/schemas/{schema_name}"})


def main() -> int:
    manifest = json.loads((EXAMPLES / "manifest.json").read_text(encoding="utf-8"))
    components = apds_components()
    failures = 0

    for spec, patches in (("CDS", CDS_PATCHES), ("APDS", APDS_PATCHES)):
        for name, (reason, _) in patches.items():
            print(f"NOTE  {spec} {name}: {reason}")

    for entry in manifest:
        payload = json.loads((EXAMPLES / entry["file"]).read_text(encoding="utf-8"))
        if entry["spec"] == "cds":
            validator = cds_validator(entry["schema"])
        else:
            validator = apds_validator(entry["schema"], components)
        errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.path))
        label = f"{entry['file']}  ({entry['spec']}:{entry['schema']})"
        if not errors:
            print(f"ok    {label}")
            continue
        failures += 1
        print(f"FAIL  {label}")
        for err in errors:
            where = "/".join(str(p) for p in err.path) or "<root>"
            print(f"        {where}: {err.message[:200]}")

    print(f"\n{len(manifest) - failures}/{len(manifest)} examples valid")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
