# Monitoring

The service has one status endpoint and writes logs to the console. There is no metrics endpoint.

## `GET /health`

```bash
curl -s http://localhost:8080/health
```

```json
{ "success": true, "data": { "status": "ok", "links": 3, "last_sync": "2026-06-01T12:00:00Z" }, "error": null }
```

| Field | Meaning |
|---|---|
| `status` | Always `ok` while the process answers |
| `links` | Number of links in the registry now. `0` before the first sync |
| `last_sync` | UTC time of the last successful full sync, to the second, or `null` if none yet |

`/health` never calls CDS or APDS and never triggers a sync. Use it for liveness only.

What to watch:

1. **Liveness:** `/health` returns 200.
2. **Sync freshness:** `last_sync` is not `null` and not older than your sync interval. Webhook updates do not
   change `last_sync`; only a full sync does.
3. **Link count:** a sudden drop in `links` after a sync usually means an upstream returned less data than
   before.
4. **Upstream reachability:** `/health` cannot show this. Call `POST /sync` (or `GET /issues`) from your
   monitor and alert on `502`. Remember that `POST /sync` loads both upstreams.
5. **Data quality:** `GET /issues` lists broken and one-sided references (`apds_target_missing`,
   `cds_target_missing`, `stale_cds_reference`, `invalid_reference`). See the
   [data model](../developer/data-model.md#issues). A growing list means publishers need to fix references.

## What is logged

| | Python | TypeScript |
|---|---|---|
| Where | stderr, plain text: `<time> <LEVEL> <logger> <message>` | stdout, JSON lines (Fastify / pino) |
| Level | INFO and above | info and above |
| Request (access) logs | Off (uvicorn `access_log=False`) | Off (`disableRequestLogging`) |
| Startup | uvicorn start-up lines | `Server listening at ...` |
| Each sync | `sync complete: <n> links, <m> issues` (INFO) | nothing |
| Upstream failures | `upstream failure: <message>` (WARNING) | `upstream failure: <message>` (warn) |
| Unexpected errors | uvicorn traceback | `unexpected error: <error name>` (error) |
| Outgoing upstream requests | **one INFO line per request from `httpx`, with the full URL** | nothing |

Upstream failure messages name only the upstream and the path, for example
`APDS returned HTTP 401 for /places` or `CDS request to /curbs/zones failed: ConnectError`. They never
include query strings.

Access logs are off on purpose: request lines can carry identifiers that must not be logged.

## What is never logged

- **Upstream tokens** (`CDS_TOKEN`, `APDS_TOKEN`) and the webhook token. They are not logged and not returned
  in responses.
- **Request bodies**, including the credential sent to `POST /permits/verify`. Responses show only the masked
  form (`credential_masked`, for example `ZA-***217`).

**Known exception (Python only):** the `httpx` INFO line for the APDS permit lookup contains the full URL,
and that URL carries `credential_id=<plate or permit>` in clear text. This breaks the rule in profile §2.5.
There is no setting to turn it off. Draft **PR #3** fixes it. Until then, treat Python logs as personal data:
restrict access, keep retention short, and do not ship them to shared log systems.

## Pending changes

- **PR #3:** stops the Python `httpx` request log (see above).
- **PR #4:** the Python version will answer unknown routes and unexpected errors with the JSON envelope
  (`not_found`, `internal_error`), as the TypeScript version already does.
