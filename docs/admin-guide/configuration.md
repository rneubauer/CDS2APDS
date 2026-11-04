# Configuration

The service is configured **only** through environment variables. There is no config file. The names are
listed in [`.env.example`](../../.env.example); the contract is in
[docs/03 §3.1](../03-link-service.md#31-configuration-environment-variables). Both versions read the same
variables with the same rules (`config.py` and `config.ts`).

The service does not load a `.env` file by itself. Set the variables in your shell, your process manager
(for example a systemd `EnvironmentFile=`), or your container runtime. Never commit real values.

## Variables

| Variable | Required | Default | Allowed values | Effect |
|---|---|---|---|---|
| `CDS_BASE_URL` | **yes** | | Absolute `http://` or `https://` URL | Root of the CDS server. The service appends `/curbs/zones`, `/curbs/policies`, and so on |
| `CDS_TOKEN` | no | none | Any string | If set, sent to CDS as `Authorization: Bearer <CDS_TOKEN>` |
| `APDS_BASE_URL` | **yes** | | Absolute `http://` or `https://` URL | Root of the APDS server **including** the version prefix, e.g. `https://apds.example.org/v4`. The service appends `/places`, `/rights/specs`, `/rights/assigned` |
| `APDS_TOKEN` | no | none | Any string | If set, sent to APDS in the header chosen by `APDS_AUTH_SCHEME` |
| `APDS_AUTH_SCHEME` | no | `bearer` | `bearer` or `mcc` (case-insensitive) | `bearer` sends `Authorization: Bearer <APDS_TOKEN>`. `mcc` sends `X-MCC-Access-Token: <APDS_TOKEN>` (legacy APDS servers). Has no effect when `APDS_TOKEN` is not set |
| `LINK_WEBHOOK_TOKEN` | no | none | Any string | If set, `POST /webhooks/apds` requires the header `X-Link-Webhook-Token` with exactly this value (compared in constant time). If not set, the webhook route is open |
| `DEFAULT_RADIUS_M` | no | `400` | Integer 1 to 5000 | Search radius in metres for `GET /zones/{id}/off-street` when the caller gives no `radius_m` |
| `HTTP_TIMEOUT_MS` | no | `10000` | Integer 100 to 120000 | Timeout in milliseconds for each upstream call |
| `HOST` | no | `0.0.0.0` | Any listen address | Address the HTTP server binds to |
| `PORT` | no | `8080` | Integer 1 to 65535 | Port the HTTP server listens on |

## Parsing rules

These apply to both versions.

- **Empty means unset.** A variable set to an empty string gets its default (or counts as missing, for the two
  required URLs).
- **URLs** are trimmed, must parse as an absolute `http` or `https` URL, and lose any trailing `/`.
- **Integers** must be plain digits (surrounding spaces are allowed). No sign, no decimals, no units.
  A value outside the range stops the service at start.
- **Tokens** are used exactly as given. They are not trimmed, so a stray newline or space in a secrets file
  becomes part of the header.
- **`APDS_AUTH_SCHEME`** is trimmed and lower-cased before it is checked.

If a value is invalid the service prints one of these to stderr and exits with code 2:

| Message | Cause |
|---|---|
| `configuration error: CDS_BASE_URL is required` | Required URL not set (same for `APDS_BASE_URL`) |
| `configuration error: CDS_BASE_URL must be an absolute http(s) URL` | No scheme, wrong scheme, or not a URL |
| `configuration error: PORT must be an integer` | Non-digit characters in an integer variable |
| `configuration error: PORT must be between 1 and 65535` | Integer out of range (same pattern for `DEFAULT_RADIUS_M`, `HTTP_TIMEOUT_MS`) |
| `configuration error: APDS_AUTH_SCHEME must be one of bearer, mcc` | Unknown scheme |

## Timeout detail

`HTTP_TIMEOUT_MS` applies to each upstream request on its own; a sync makes several. The two versions apply
it slightly differently:

- **Python** (httpx) uses it as the connect, read, write and pool timeout separately.
- **TypeScript** (`fetch` with `AbortSignal.timeout`) uses it as one deadline for the whole request,
  including reading the body.

A timeout becomes `502 upstream_error` for the caller.

## Example

A local `.env` file for a process manager (placeholder values only):

```bash
CDS_BASE_URL=https://cds.example.org
CDS_TOKEN=<cds-bearer-token>
APDS_BASE_URL=https://apds.example.org/v4
APDS_TOKEN=<apds-token>
APDS_AUTH_SCHEME=bearer
LINK_WEBHOOK_TOKEN=<long-random-string>
DEFAULT_RADIUS_M=400
HTTP_TIMEOUT_MS=10000
HOST=127.0.0.1
PORT=8080
```

Changes take effect only after a restart.
