# Known limits

Checked against the code in v0.1. Values are the same in both versions unless a row says otherwise.

## Capacity

| Limit | Value | Where in code | What happens |
|---|---|---|---|
| Registry entries added by webhook | 100 000 HierarchyElements and 100 000 RightSpecifications | `MAX_REGISTRY_ENTRIES` in `registry.py` / `registry.ts` | A webhook that would add a **new** id beyond the cap gets `400 invalid_request` ("registry is full"). Updates to known ids and deletions always apply. A full sync is not capped by this value |
| APDS pages per listing | 1000 pages | `MAX_PAGES` in `upstream.py` / `upstream.ts` | Reading more fails with `502` "exceeded 1000 pages". The service does not set a page size, so the real ceiling is 1000 × the APDS server's page size. Applies to `/places`, `/rights/specs` and `/rights/assigned` |
| APDS paging stop | | `ApdsClient` paging | Paging stops at an empty page, when `meta.total` items are read, or when `meta.total` is missing or not an integer (then only the pages read so far count) |
| CDS listings | One request each | `CdsClient` | `/curbs/zones`, `/curbs/areas`, `/curbs/policies`, `/curbs/objects` are read in one call each, with no paging and no query parameters (so no historic records) |
| Request body | 1 MiB | `MAX_BODY_BYTES` in `app.py`; Fastify default `bodyLimit` | `400 invalid_request` |
| `radius_m` | 1 to 5000 metres | `_parse_radius` / `parseRadius` | `400 invalid_request` |
| `DEFAULT_RADIUS_M` | 1 to 5000 | `config` | Service refuses to start |
| `HTTP_TIMEOUT_MS` | 100 to 120000 ms per upstream call | `config` | Service refuses to start |

## State

- **In memory only.** The registry is not persisted. A restart empties it; the next request that needs it
  triggers a full sync. See [Backup and restore](backup-restore.md).
- **One registry per process.** Replicas do not share state, and a webhook reaches only one replica.
- **No scheduled sync.** CDS changes are seen only after `POST /sync`. Run it from a scheduler.
- **Webhooks rebuild from the last CDS harvest.** A webhook never re-reads CDS, so CDS changes since the last
  sync are not visible after a webhook either.
- **Webhook bodies are stored as sent.** Apart from requiring a string `id`, the service does not validate a
  webhook payload before it upserts it.

## Features not in v0.1

- **No caller authentication, roles or rate limiting.** Only the webhook route can be protected
  (`LINK_WEBHOOK_TOKEN`). Use a gateway or network rules for everything else.
- **No TLS.** Terminate TLS at a reverse proxy.
- **No metrics endpoint.** `/health` gives the link count and last sync time only, and does not check the
  upstreams.
- **No log-level setting.** Python logs at INFO, TypeScript at info.
- **Curb spaces are not harvested.** The service reads CDS zones, areas, policies and objects, not spaces.
  An APDS reference with `className: CdsCurbSpace` is always reported as `cds_target_missing` and dropped.
- **Only `Place*` and `RightSpecification*` webhooks change state.** Other APDS events are accepted and
  ignored (`"applied": false`). Assigned rights are always read live during a permit check.

## Known defects (fixes in draft PRs, not merged)

| Defect | Version | Pending fix |
|---|---|---|
| Upstream request URLs, including the permit credential, are logged at INFO by `httpx` | Python | PR #3 |
| `fetch` follows upstream redirects, which could send the credential query and the APDS token to another host | TypeScript | PR #3 |
| Unknown routes and crashes do not use the JSON envelope; some malformed upstream or webhook data can cause a 500 until the next `POST /sync` | Python | PR #4 |
| Small validation differences between the versions (impossible dates in `at`, repeated query parameters, ids `.` and `..`, tie-break order of issues) | both | PR #5, PR #6 |
