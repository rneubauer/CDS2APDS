# Backup and restore

**There is nothing to back up.** The link service is stateless across restarts. It keeps no database and
writes no files. All parking data lives in the CDS and APDS servers; back those up according to their own
guides.

## What the service holds in memory

- A copy of the last CDS and APDS harvest.
- The links and issues derived from it.
- The time of the last full sync (`last_sync`).
- Any changes applied by APDS webhooks since that sync.

## What happens on restart

1. The process starts with an empty registry. `GET /health` shows `links: 0` and `last_sync: null`.
2. The first request that needs links (`GET /links`, `GET /issues`, `GET /zones/{id}/off-street`,
   `POST /webhooks/apds`) or an explicit `POST /sync` re-harvests both upstreams. That first request is
   slower than usual.
3. After the sync, the registry reflects the upstreams as they are **now**. Webhook changes received before
   the restart are not lost in practice, because APDS already holds them and the sync reads them again.
4. If an upstream is down at that moment, those requests return `502 upstream_error` until it is back.

`POST /permits/verify` does not use the registry, so it works right after a restart as long as both
upstreams answer.

## Recommended restart routine

1. Restart the service.
2. Warm the registry straight away so the first real caller does not pay for the sync:
   ```bash
   curl -fsS -X POST http://127.0.0.1:8080/sync > /dev/null
   ```
3. Confirm `GET /health` shows a recent `last_sync` and the expected `links` count.

## What to keep safe instead

- The environment file with `CDS_TOKEN`, `APDS_TOKEN` and `LINK_WEBHOOK_TOKEN`. Keep it in your secret store.
- The webhook registration on the APDS server, if you use webhooks.
