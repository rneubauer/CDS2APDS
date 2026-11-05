# Running in production-like setups

v0.1 is a reference implementation. It runs fine as a long-lived service, but it has no caller
authentication, rate limiting or TLS of its own. Put it behind something that does.

## 1. Run one process per registry

Each process keeps its own in-memory registry.

- The Python version starts uvicorn with **one worker**. The TypeScript version is one Node process.
- If you run several replicas behind a load balancer, each one syncs on its own, and an APDS webhook updates
  only the replica that receives it. Replicas can then disagree about links until the next `POST /sync`.
- For v0.1, run a single instance, or send webhooks and `POST /sync` to every replica.

## 2. Choose the bind address

- `HOST` defaults to `0.0.0.0`, which listens on every interface. Behind a reverse proxy on the same host,
  set `HOST=127.0.0.1` so the service is reachable only through the proxy.
- `PORT` defaults to `8080`.

## 3. Put it behind a reverse proxy

The service speaks plain HTTP and serves its routes at the root path (`/health`, `/sync`, ...).

1. Terminate TLS at the proxy.
2. If you publish it under a path prefix (for example `/link/`), have the proxy strip the prefix. The service
   has no base-path setting.
3. Restrict who can call it. The service does not authenticate callers. In particular:
   - `POST /permits/verify` answers whether a credential holds a valid permit. Expose it only to trusted
     enforcement systems.
   - `POST /sync` makes a full harvest of both upstreams on every call. Limit it to operators or a scheduler.
   - `POST /webhooks/apds` should accept traffic only from the APDS server (see step 5).
4. Keep request bodies small. The service rejects bodies over 1 MiB itself, but a proxy limit is cheaper.
5. Do not log request bodies at the proxy. `POST /permits/verify` carries licence plates and permit numbers
   in its body.

The service does not use the client address, so `X-Forwarded-*` headers need no special setup.

## 4. Health check

Use `GET /health` for liveness checks. It always returns 200 while the process is up and never calls the
upstream servers. It does **not** tell you whether CDS or APDS are reachable; see [Monitoring](monitoring.md).

## 5. Protect the webhook

APDS can push `Place*` and `RightSpecification*` events to `POST /webhooks/apds`
([profile §2.7](../02-link-profile.md#27-change-notification)).

1. Generate a long random value and set it as `LINK_WEBHOOK_TOKEN`.
2. When you register the webhook with APDS (`POST {apds-base}/webhooks`), configure it to send two headers:
   - `X-Link-Webhook-Token: <your LINK_WEBHOOK_TOKEN>`
   - `X-APDS-Event-Type: <event type>`, for example `PlaceUpdated`. This header is required.
3. Also restrict the route at the network level (allow only the APDS server's addresses). APDS defines no
   signature scheme, so the token is the only check inside the service.

If `LINK_WEBHOOK_TOKEN` is empty or unset, anyone who can reach the route can change the registry.

## 6. Upstream authentication

| Upstream | Variable | Header sent |
|---|---|---|
| CDS | `CDS_TOKEN` | `Authorization: Bearer <CDS_TOKEN>` |
| APDS, `APDS_AUTH_SCHEME=bearer` (default) | `APDS_TOKEN` | `Authorization: Bearer <APDS_TOKEN>` |
| APDS, `APDS_AUTH_SCHEME=mcc` | `APDS_TOKEN` | `X-MCC-Access-Token: <APDS_TOKEN>` (legacy APDS servers) |

If a token is not set, no auth header is sent. Tokens are read from the environment only and are never
returned in responses. Store them in your secret store or a root-only environment file, not in the repo.

## 7. Keep CDS links fresh

CDS has no change notifications, and the service has no built-in scheduler. Links from CDS change only on
`POST /sync`. Call it from a scheduler (for example cron or a systemd timer) at an interval that suits how
often your curb data changes:

```bash
curl -fsS -X POST http://127.0.0.1:8080/sync > /dev/null
```

The response contains every link and issue, so discard it or save it for review.

## 8. Example: systemd unit (Python version)

Placeholders only; adjust paths and user.

```ini
[Unit]
Description=CDS-APDS link service
After=network-online.target

[Service]
User=cdsapds
WorkingDirectory=/opt/CDS2APDS/services/python
EnvironmentFile=/etc/cds-apds-link.env
ExecStart=/opt/CDS2APDS/services/python/.venv/bin/cds-apds-link
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

For the TypeScript version use `WorkingDirectory=/opt/CDS2APDS/services/typescript` and
`ExecStart=/usr/bin/node dist/server.js`.

Make `/etc/cds-apds-link.env` readable only by root and the service user, since it holds the tokens.

## Pending changes

- **PR #3** (draft): the Python version will stop logging upstream request URLs, which today include the
  presented credential (see [Monitoring](monitoring.md#what-is-logged)); the TypeScript version will stop
  following upstream redirects. There is no setting to turn the Python request log off. Until PR #3 merges,
treat Python logs as personal data and keep them private, or run the TypeScript version.
