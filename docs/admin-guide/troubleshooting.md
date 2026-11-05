# Troubleshooting

Every API error comes back in the envelope
`{ "success": false, "data": null, "error": { "code": "...", "message": "..." } }`
([docs/03 §3.2](../03-link-service.md#32-response-envelope)). Start with `error.code` and `error.message`.

| HTTP | `error.code` | Typical cause |
|---|---|---|
| 400 | `invalid_request` | Bad parameter or body, missing webhook header, registry full |
| 401 | `unauthorized` | Webhook token missing or wrong |
| 404 | `not_found` | The curb zone does not exist upstream |
| 502 | `upstream_error` | CDS or APDS failed, timed out, or returned something unexpected |

## The service exits at start

The process prints `configuration error: <reason>` to stderr and exits with code 2.

| Message | Fix |
|---|---|
| `CDS_BASE_URL is required` / `APDS_BASE_URL is required` | Set both variables. Check that your process manager really passes them (an empty value counts as missing) |
| `... must be an absolute http(s) URL` | Include the scheme: `https://cds.example.org`, not `cds.example.org` |
| `... must be an integer` | Use plain digits: `PORT=8080`, not `8080/tcp` or `8e3` |
| `... must be between X and Y` | `DEFAULT_RADIUS_M` 1–5000, `HTTP_TIMEOUT_MS` 100–120000, `PORT` 1–65535 |
| `APDS_AUTH_SCHEME must be one of bearer, mcc` | Use `bearer` or `mcc` |

If the settings are fine but the port is taken, the Python version shows a uvicorn bind error and the
TypeScript version logs the listen error and exits with code 1. Change `PORT` or stop the other process.

## 502 `upstream_error`

The message tells you which upstream and which path failed. It never contains query strings.

| Message pattern | Likely cause | Fix |
|---|---|---|
| `CDS request to /curbs/zones failed: ConnectError` (Python) or `...failed: TypeError` (TypeScript) | Host unreachable, DNS or TLS failure | Check the URL, DNS, firewall and certificates from the service host: `curl -v <CDS_BASE_URL>/curbs/zones` |
| `... failed: ReadTimeout` / `ConnectTimeout` (Python) or `... failed: TimeoutError` (TypeScript) | Upstream slower than `HTTP_TIMEOUT_MS` | Raise `HTTP_TIMEOUT_MS` (max 120000) or fix the upstream |
| `APDS returned HTTP 401 for /places` (or 403) | Missing or wrong token, or wrong header | Check `APDS_TOKEN` and `APDS_AUTH_SCHEME` (`bearer` vs `mcc`). Check the token has no trailing newline. Same for `CDS_TOKEN` |
| `APDS returned HTTP 404 for /places` | `APDS_BASE_URL` lacks the version prefix | Use the root **including** `/v4`, e.g. `https://apds.example.org/v4` |
| `CDS returned HTTP 404 for /curbs/zones` | `CDS_BASE_URL` points at the wrong root | Use the root that `/curbs/...` hangs off. Do not include `/curbs` yourself |
| `... returned invalid JSON for ...` | The upstream answered with HTML or text (often a login page or proxy error) | Call the URL with curl and check what comes back |
| `malformed CDS zones data` / `malformed APDS /places data` | The response does not have the expected shape | CDS lists must look like `{"data":{"zones":[...]}}`; APDS lists like `{"data":[...],"meta":{"total":N}}` |
| `APDS /places exceeded 1000 pages` | Very large dataset, or the server ignores `page` and returns the same page forever | See [Known limits](known-limits.md) |
| `curb zone <id> has unusable geometry: ...` | The zone's geometry is not a usable GeoJSON Point, LineString or Polygon | Fix the zone in the CDS data |

A sync needs **all six** list reads (CDS zones, areas, policies, objects; APDS places, right specifications)
to succeed. One failure fails the whole sync and leaves the registry unchanged. A 404 on `/curbs/objects` is
fine; it means "no objects".

If the registry has never synced, every request that needs links (`/links`, `/issues`, `/zones/{id}/off-street`,
`/webhooks/apds`) tries to sync and returns 502 until the upstreams work.

## Webhook returns 401 `unauthorized`

Message: `missing or invalid webhook token`.

1. `LINK_WEBHOOK_TOKEN` is set on the service, so the header `X-Link-Webhook-Token` is required.
2. Check that APDS sends that header with exactly the same value. Case and whitespace matter.
3. Check the service and APDS use the same secret after a rotation. The service reads it only at start, so
   restart it after changing the value.

## Webhook returns 400 `invalid_request`

| Message | Fix |
|---|---|
| `X-APDS-Event-Type header is missing or not an APDS EventTypeEnum value` | Send the header with a value such as `PlaceUpdated`. Allowed: `Created`, `Updated` or `Deleted` after `AssignedRight`, `Session`, `Place`, `RightSpecification`, `Rate` or `Organisation` |
| `event data must include an id` | The body must be a JSON object with a non-empty string `id` |
| `request body must be JSON` / `request body must be a JSON object` | Send a JSON object with `Content-Type: application/json` |
| `request body is too large` | Bodies over 1 MiB are refused |
| `invalid request` (TypeScript) | Fastify rejected the body before the service saw it: not valid JSON, wrong `Content-Type`, or over 1 MiB. The Python version gives the more specific messages above |
| `registry is full; new APDS elements are refused` | The 100 000 entry cap is reached. See [Known limits](known-limits.md) |

Events for `AssignedRight`, `Session`, `Rate` and `Organisation` are accepted with `"applied": false`. That is
expected; they do not affect links.

## Off-street summary errors

| Response | Cause | Fix |
|---|---|---|
| 400 `radius_m must be an integer from 1 to 5000` | `radius_m` out of range, or not plain digits | Use 1–5000 metres. Note that CDS radii are in centimetres; APDS and this service use metres |
| 404 `curb zone <id> not found` | CDS returned 404 for that zone | Check the id against `GET <CDS_BASE_URL>/curbs/zones` |
| Place shows `spaces_available: null` | APDS has no supply quantity or occupancy for it | Expected; the service never guesses availability |

## Permit check surprises

| Result | Meaning |
|---|---|
| `no_programme` | None of the zone's policies has a permit rule **and** an APDS reference to `rights/specs`. Check the CDS policies |
| `not_found` | No assigned right under the programme holds that credential |
| `programme_inactive` | The RightSpecification is `suspended` or `planned`, outside its overall time window, or could not be read |
| `expired` / `not_yet_valid` | The right's `expiry` or `issuanceTime` rules it out at the checked time. An unreadable timestamp fails closed |

400 messages for this endpoint: `curb_zone_id is required`, `credential is required`,
`credential_type must be 'permit' or 'licensePlate'`, `at must be an ISO-8601 instant`.

## Links look stale or missing

1. Call `POST /sync`. CDS changes are only picked up by a sync.
2. Check `GET /issues` for `apds_target_missing`, `cds_target_missing` and `invalid_reference`.
3. A link to a curb **space** (`className: CdsCurbSpace`) always shows as `cds_target_missing` in v0.1. See
   [Known limits](known-limits.md).
4. After a restart the registry is empty until the next request that needs it.

## Unknown route

- TypeScript: `404` with `error.code` `not_found` and message `route not found`.
- Python: `404` with FastAPI's own body, `{"detail":"Not Found"}` (not the envelope). A wrong method gives
  `405`. An unexpected crash gives a plain-text `500 Internal Server Error`.

**Pending change:** draft **PR #4** makes the Python version return the envelope (`404 not_found`,
`500 internal_error`) like the TypeScript version.
