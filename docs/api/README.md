# API reference: link service

For integrators who call the CDS-APDS link service over HTTP. Both reference services (Python and
TypeScript) expose the same API, so this page applies to both.

| File | What it is |
|---|---|
| [`openapi.json`](openapi.json) | OpenAPI 3.1 document **generated** from the Python service by [`tools/gen_openapi.py`](../../tools/gen_openapi.py). Do not edit it by hand. |
| This README | What the generated file covers, the gaps it has, and a copy-paste `curl` example for every endpoint. |

The **normative** description of each endpoint is [docs/03-link-service.md §3.4](../03-link-service.md#34-endpoints).
Where this page and docs/03 disagree, docs/03 wins.

## Regenerating `openapi.json`

```sh
pip install -e services/python
python tools/gen_openapi.py          # rewrite docs/api/openapi.json
python tools/gen_openapi.py --check  # exit 1 if the committed copy is stale
```

The script builds the app with dummy settings and makes no network calls. CI (`.github/workflows/docs.yml`)
regenerates the file on every push and pull request and fails if the committed copy differs. If you change a
route, commit the regenerated file in the same PR.

## What the generated file covers, and what it misses

The Python service reads most inputs by hand (query string, headers, JSON body) so it can return the same
error envelope as the TypeScript service. FastAPI can only describe what it parses itself, so the generated
document is a **route list**, not a full contract.

| Covered | Missing (read docs/03 instead) |
|---|---|
| All seven paths and their HTTP methods | Request bodies of `POST /permits/verify` and `POST /webhooks/apds` |
| Query parameters FastAPI parses itself: today `cds_id`, `apds_id`, `kind` on `GET /links` (they drop out of the file if that route switches to hand parsing, as the open PR #5 does) | `radius_m` on the off-street endpoint |
| The `{zone_id}` path parameter | Headers `X-APDS-Event-Type` and `X-Link-Webhook-Token` |
| Service title and version | Response schemas: the generated file says only "Successful Response" and doesn't describe the `{success, data, error}` envelope ([§3.2](../03-link-service.md#32-response-envelope)) or the Link and Issue objects ([§3.3](../03-link-service.md#33-registry-and-sync)) |
| | Error statuses. The file lists `422` with FastAPI's `HTTPValidationError`, but the service never returns 422: invalid input gets `400 invalid_request` in the envelope |

**Known gap:** a richer reference needs doc comments, Pydantic request and response models, and `responses=`
declarations on the routes in `services/python/src`. That is a service change, which should go through
`conformance/` and both services together (see [AGENTS.md](../../AGENTS.md)). It hasn't been done yet.

## Endpoints

| Endpoint | What it does | Normative text |
|---|---|---|
| `GET /health` | Liveness and link count. Never syncs. | [§3.4 GET /health](../03-link-service.md#get-health) |
| `POST /sync` | Re-reads both upstreams and rebuilds the links. | [§3.4 POST /sync](../03-link-service.md#post-sync) |
| `GET /links` | Lists links, filtered by `cds_id`, `apds_id`, `kind`. | [§3.4 GET /links](../03-link-service.md#get-linkscds_idapds_idkind) |
| `GET /issues` | Lists broken or one-sided references. | [§3.4 GET /issues](../03-link-service.md#get-issues) |
| `GET /zones/{curb_zone_id}/off-street` | Nearby garages and lots for a curb zone, with availability. | [§3.4 off-street](../03-link-service.md#get-zonescurb_zone_idoff-streetradius_m) |
| `POST /permits/verify` | Checks a permit or plate against the zone's permit programmes. | [§3.4 POST /permits/verify](../03-link-service.md#post-permitsverify) |
| `POST /webhooks/apds` | Receives APDS change events. | [§3.4 POST /webhooks/apds](../03-link-service.md#post-webhooksapds) |

Every response uses the envelope `{ "success": true|false, "data": ..., "error": null | { "code", "message" } }`.

## Examples

The examples assume a service on `http://localhost:8080` (the default `PORT`) whose upstreams serve the
fictional "Civic District" data in [`examples/`](../../examples). The ids, permit `ZA-004217` and plate `EXM1234`
are made up. The webhook examples assume `LINK_WEBHOOK_TOKEN=example-token`.

The first line of each block (`# -> 200`) is the expected HTTP status.
`services/python/tests/test_api_examples.py` runs every block below against the Python service with the
in-memory fake upstream, so a failing example fails CI. If you add an example, keep that format.

### Health

```sh
# -> 200
curl -s http://localhost:8080/health
```

### Sync both upstreams

```sh
# -> 200
curl -s -X POST http://localhost:8080/sync
```

### Links for one curb zone

```sh
# -> 200
curl -s 'http://localhost:8080/links?cds_id=3f2a9c1e-5b7d-4e8a-9c01-00000000b001'
```

### Permit links only

```sh
# -> 200
curl -s 'http://localhost:8080/links?kind=permit'
```

### Issues

```sh
# -> 200
curl -s http://localhost:8080/issues
```

### Off-street parking near a curb zone

```sh
# -> 200
curl -s 'http://localhost:8080/zones/3f2a9c1e-5b7d-4e8a-9c01-00000000b001/off-street?radius_m=400'
```

The first place returned is the linked Civic Garage (`7d41e6b2-8c3f-4a9d-b210-00000000f001`), with `spaces_available`.

### Off-street with an invalid radius (error envelope)

```sh
# -> 400
curl -s 'http://localhost:8080/zones/3f2a9c1e-5b7d-4e8a-9c01-00000000b001/off-street?radius_m=9999'
```

Returns `{"success": false, "data": null, "error": {"code": "invalid_request", ...}}`.

### Verify a permit

The credential goes in the body, never in the URL. The response masks it (`ZA-***217`).

```sh
# -> 200
curl -s -X POST http://localhost:8080/permits/verify \
  -H 'Content-Type: application/json' \
  -d '{"curb_zone_id": "3f2a9c1e-5b7d-4e8a-9c01-00000000b003", "credential": "ZA-004217", "credential_type": "permit", "at": "2026-06-01T12:00:00Z"}'
```

`result` is `valid`. With `"credential": "ZA-999999"` it is `not_found`.

### Verify a licence plate

```sh
# -> 200
curl -s -X POST http://localhost:8080/permits/verify \
  -H 'Content-Type: application/json' \
  -d '{"curb_zone_id": "3f2a9c1e-5b7d-4e8a-9c01-00000000b003", "credential": "EXM1234", "credential_type": "licensePlate", "at": "2026-06-01T12:00:00Z"}'
```

### APDS webhook: a place was deleted

```sh
# -> 200
curl -s -X POST http://localhost:8080/webhooks/apds \
  -H 'Content-Type: application/json' \
  -H 'X-APDS-Event-Type: PlaceDeleted' \
  -H 'X-Link-Webhook-Token: example-token' \
  -d '{"id": "7d41e6b2-8c3f-4a9d-b210-00000000f004", "version": 1}'
```

Returns `{"event_type": "PlaceDeleted", "applied": true}`.

### APDS webhook: an event the service ignores

```sh
# -> 200
curl -s -X POST http://localhost:8080/webhooks/apds \
  -H 'Content-Type: application/json' \
  -H 'X-APDS-Event-Type: SessionCreated' \
  -H 'X-Link-Webhook-Token: example-token' \
  -d '{"id": "example-session-1", "version": 1}'
```

Returns `"applied": false`.

### APDS webhook without the token

```sh
# -> 401
curl -s -X POST http://localhost:8080/webhooks/apds \
  -H 'Content-Type: application/json' \
  -H 'X-APDS-Event-Type: PlaceDeleted' \
  -d '{"id": "7d41e6b2-8c3f-4a9d-b210-00000000f004"}'
```
