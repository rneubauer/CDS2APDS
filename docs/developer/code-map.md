# Code map

## Top level

| Path | What it is |
|---|---|
| `AGENTS.md` | Handoff notes: project rules and the three checks every PR must pass |
| `CLAUDE.md` | Extra notes for Claude Code agents; points to `AGENTS.md` |
| `README.md` | Project overview and quick start |
| `.env.example` | Names of all service environment variables (no values) |
| `.gitignore` | Ignores virtualenvs, `node_modules/`, `dist/`, coverage output and `.env` |
| `.github/workflows/ci.yml` | CI: example validation, Python tests (3.11, 3.13, coverage at least 80%), TypeScript typecheck, tests and build (Node 20, 22) |
| `docs/` | Boundary, profile, service contract, decision records, and these guides |
| `docs/cds-apds-link-profile.html` | Standalone rendering of the profile for sharing. Keep it in sync with `docs/02-link-profile.md` |
| `examples/` | Worked example payloads for a fictional "Civic District" |
| `conformance/` | Language-neutral test cases and fixtures that every service must pass |
| `services/python/` | Python reference link service (FastAPI) |
| `services/typescript/` | TypeScript reference link service (Fastify) |
| `tools/validate_examples.py` | Validates every example against the vendored schemas |
| `vendor/` | Pinned, unmodified copies of the CDS 1.1 and APDS 4.1 schemas, with their licences |

## Python service: `services/python/`

Package `cds_apds_link` in `src/`. Build metadata in `pyproject.toml` (package version 0.1.0).

| Module | What it does |
|---|---|
| `__init__.py` | Exports `create_app`, `Settings` and `__version__` |
| `__main__.py` | Process entry point (`python -m cds_apds_link` or the `cds-apds-link` script). Reads the environment, sets up logging, starts uvicorn with access logs off. Exits with code 2 on a configuration error |
| `config.py` | `Settings.from_env()`: reads and validates the environment variables |
| `errors.py` | `ServiceError` and helpers for the four error codes (`invalid_request`, `unauthorized`, `not_found`, `upstream_error`) |
| `upstream.py` | `CdsClient` and `ApdsClient`: auth headers, APDS paging, percent-encoding of ids, and checks that turn bad upstream responses into `upstream_error` |
| `registry.py` | Harvests `external_references` and `operatorDefinedReference`, resolves link kinds, merges links, reports issues. Holds the in-memory `Registry` |
| `offstreet.py` | T2: builds the nearby off-street summary for a curb zone |
| `permits.py` | T3: finds permit programmes, normalises and masks credentials, parses timestamps, evaluates assigned rights |
| `geo.py` | Centroid of a zone geometry, haversine distance, half-up rounding |
| `app.py` | `LinkService` (orchestration: sync, live reads, webhooks) and `create_app()` (routes, response envelope, error mapping, body size limit, webhook token check) |

Tests in `tests/`:

| File | What it does |
|---|---|
| `conftest.py` | Puts `tests/` on the import path so `fake_upstream` can be imported |
| `fake_upstream.py` | In-memory CDS and APDS servers (an `httpx.MockTransport`) that follow `conformance/fixtures.json` |
| `test_conformance.py` | Runs every case in `conformance/cases.json` |
| `test_units.py` | Unit tests for edge cases not covered by the shared suite |

## TypeScript service: `services/typescript/`

ES modules, compiled by `tsc` from `src/` to `dist/`. Build metadata in `package.json` (version 0.1.0).

| Module | What it does |
|---|---|
| `server.ts` | Process entry point (`npm start` runs `dist/server.js`). Reads the environment, starts Fastify. Exits with code 2 on a configuration error, 1 if it cannot listen |
| `config.ts` | `settingsFromEnv()`: reads and validates the environment variables |
| `errors.ts` | `ServiceError` and helpers for the four error codes |
| `json.ts` | Type guards for untrusted JSON (`isObject`, `isString`, ...) and a code-point string compare that matches Python's ordering |
| `upstream.ts` | `CdsClient` and `ApdsClient`: auth headers, APDS paging, timeouts, id encoding, untrusted-response checks |
| `registry.ts` | Same job as `registry.py` |
| `offstreet.ts` | Same job as `offstreet.py` |
| `permits.ts` | Same job as `permits.py` |
| `geo.ts` | Same job as `geo.py` |
| `service.ts` | `LinkService`: orchestration (sync, live reads, webhooks). In Python this class lives in `app.py` |
| `app.ts` | `buildApp()`: routes, response envelope, error mapping, webhook token check |

Tests in `test/`:

| File | What it does |
|---|---|
| `fake-upstream.ts` | In-memory CDS and APDS servers (a `fetch` replacement) that follow `conformance/fixtures.json` |
| `conformance.test.ts` | Runs every case in `conformance/cases.json` |
| `units.test.ts` | Unit tests for edge cases not covered by the shared suite |

Other files: `tsconfig.json` (strict, ES2022, NodeNext), `vitest.config.ts` (coverage of `src/`, excluding
`server.ts`), `package-lock.json`.

## `conformance/`

Two JSON files. Both services read them directly from the repository; there is no copy per service.

### `fixtures.json`

| Key | Meaning |
|---|---|
| `config` | Environment variables used to build the service under test (`CDS_BASE_URL`, `APDS_BASE_URL`, `LINK_WEBHOOK_TOKEN`, `DEFAULT_RADIUS_M`) |
| `cds` | Lists of example files (paths relative to `examples/`) served as CDS `zones`, `areas` and `policies` |
| `apds` | Lists of example files served as APDS `elements`, `right_specs` and `assigned_rights` |
| `fake_upstream` | Plain-language rules for the fake servers: routes, response shapes, page sizes, which query parameters are accepted (any other parameter returns 400), and how radius and credential filters work. `GET /curbs/objects` returns 404 |
| `matching` | How `expect.body` is compared (see below) |

### `cases.json`

An array of cases. Each case is:

```json
{
  "name": "short description",
  "steps": [
    {
      "request": { "method": "POST", "path": "/webhooks/apds", "headers": { "X-APDS-Event-Type": "PlaceDeleted" }, "body": { "id": "..." } },
      "expect":  { "status": 200, "body": { "success": true, "data": { "applied": true } } }
    }
  ]
}
```

- `request.headers` and `request.body` are optional. The body is sent as JSON.
- `expect.status` must match exactly.
- `expect.body` is a **subset match**: every expected key must be present and match; arrays must have the
  same length and match element by element; the string `"<any>"` matches any present value.
- Each case starts a **fresh service instance**, so the registry is empty at the start of every case.
- Steps in a case run in order against the same instance, so a later step sees the effect of an earlier one.

### How each suite runs them

| | Python (`tests/test_conformance.py`) | TypeScript (`test/conformance.test.ts`) |
|---|---|---|
| One test per case | `pytest.mark.parametrize` | one `it()` per case |
| Service | `create_app(settings, transport=..., clock=...)` with FastAPI `TestClient` | `buildApp(settings, { fetch, clock })` with `app.inject()` |
| Upstream | `FakeUpstream(FIXTURES).transport()` | `new FakeUpstream().fetch` |
| Clock | Fixed at `2026-06-01T12:00:00Z` | Fixed at `2026-06-01T12:00:00Z` |
| Matcher | `subset_match()` | `subsetMatch()` |

## `tools/`

`validate_examples.py` reads `examples/manifest.json`. For each entry it validates the file against the
named schema: a CDS model file from `vendor/cds-1.1/Shared Data Models/`, or an APDS component from
`vendor/apds-4.1/apds-api-4.1.yaml`. Before validating, it applies known upstream schema fixes in memory
(`APDS_PATCHES`, `CDS_PATCHES`) and prints a `NOTE` line for each. It prints `ok` or `FAIL` per file and exits
non-zero if any file fails. The patched defects are listed in profile §2.9.

## `vendor/`

Pinned upstream copies. Do not edit them ([ADR 0004](../decisions/0004-vendor-pinned-schemas.md)).
`vendor/README.md` lists the source repositories, the pinned commits and the licences. The services do not
read `vendor/` at runtime; only the validator does.

## `examples/`

| Path | What it is |
|---|---|
| `examples/cds/` | CDS objects: one Curb Area, three Curb Zones, three Curb Policies, one Curb Event |
| `examples/apds/` | APDS objects: three Places, one VehicularAccess, one RightSpecification, one AssignedRight |
| `examples/manifest.json` | List of `{ file, spec, schema }` entries the validator checks |

The conformance fixtures reuse these files, so a change to an example can change conformance results.
