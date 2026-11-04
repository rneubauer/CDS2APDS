# Conformance suite

Language-neutral test data that every link-service implementation must pass. Both reference services
read these two files directly from the repository. There is no copy per service.

| File | What it holds |
|---|---|
| `fixtures.json` | The fake CDS and APDS servers and the service settings used for every case |
| `cases.json` | The test cases: HTTP requests and the responses expected |

Behaviour changes go into `cases.json` first, then into both services. **Both suites must pass every case**:
`pytest` in `services/python/` (`tests/test_conformance.py`) and `npm test` in `services/typescript/`
(`test/conformance.test.ts`). CI runs both in `.github/workflows/ci.yml`. For the longer walk-through, see
[Build, run and test](../docs/developer/build-run-test.md#adding-a-conformance-case).

## `cases.json`

A JSON array of cases.

| Field | Meaning |
|---|---|
| `name` | Short description. It becomes the test name in both suites |
| `steps` | List of steps, run in order against one service instance |
| `steps[].request.method` | HTTP method |
| `steps[].request.path` | Path with the query string, for example `/links?kind=permit` |
| `steps[].request.headers` | Optional. Object of header names and values (the webhook cases use `X-APDS-Event-Type` and `X-Link-Webhook-Token`) |
| `steps[].request.body` | Optional. Sent as JSON |
| `steps[].expect.status` | HTTP status. Must be equal |
| `steps[].expect.body` | Expected JSON body, compared as described below |

### How `expect.body` is matched

Both suites use the same rules (`subset_match()` in Python, `subsetMatch()` in TypeScript):

- **Objects:** every key in the expected object must exist in the actual object and match. Extra keys in the
  actual object are ignored. This is the partial match: write only the fields the case is about.
- **Arrays:** must have the same length, and match element by element in order. There is no partial array match.
- **`"<any>"`:** matches any value, but the key must be present. A `null` counts as present.
- **Anything else** (string, number, boolean, `null`): must be equal.

Each case starts a **fresh service instance** (an empty registry). The clock is fixed at
`2026-06-01T12:00:00Z`. Steps in one case share the instance, so a later step sees the effect of an earlier one.

## `fixtures.json`

| Key | Meaning |
|---|---|
| `description` | What the file is for |
| `config` | Environment variables for the service under test: `CDS_BASE_URL`, `APDS_BASE_URL`, `LINK_WEBHOOK_TOKEN`, `DEFAULT_RADIUS_M` |
| `cds` | The CDS data the fake server serves, as file paths relative to `examples/`. Arrays: `zones`, `areas`, `policies` |
| `apds` | The APDS data the fake server serves, as file paths relative to `examples/`. Arrays: `elements` (places and vehicular access), `right_specs`, `assigned_rights` |
| `fake_upstream` | Plain-text rules for the fake CDS and APDS servers: routes, status codes, accepted query parameters, page sizes. For example, APDS `GET /places` takes `page`, `latitude`, `longitude`, `radius`, `type` and `expand`; any other parameter gives `400`. Unknown paths give `404` |
| `matching` | The matching rules above, in one sentence |

`fake_upstream` is a description, not code. Each service has its own implementation of it:
`services/python/tests/fake_upstream.py` and `services/typescript/test/fake-upstream.ts`. If you change a rule
here, change both.

The files listed under `cds` and `apds` are the payloads in [`examples/`](../examples/README.md).
Adding one to a list changes what every case sees, for example the links returned by `POST /sync`.

## Add a case

1. Add an object to the array in `cases.json`.
2. Run both suites and check that the new case fails.
3. Change both services until both pass.
4. Update `docs/03-link-service.md` (and the profile, if publishers or consumers are affected) in the same PR.

Example (written for this README, not in the suite): the first step harvests both sides. The second step
checks that `/health` now counts three links, and that `last_sync` is present without pinning its value.

```json
{
  "name": "health after sync",
  "steps": [
    { "request": { "method": "POST", "path": "/sync" },
      "expect": { "status": 200, "body": { "success": true } } },
    { "request": { "method": "GET", "path": "/health" },
      "expect": { "status": 200, "body": { "data": { "status": "ok", "links": 3, "last_sync": "<any>" } } } }
  ]
}
```
