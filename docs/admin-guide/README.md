# Admin guide

For people who install and run the CDS–APDS **link service**. The service is a small HTTP API that sits
between a CDS 1.1 server (on-street) and an APDS 4.1 server (off-street). It comes in two equivalent
versions, Python and TypeScript. Pick one; they behave the same and take the same settings.

| Page | What it covers |
|---|---|
| [Install](install.md) | Prerequisites and installation for both versions |
| [Configuration](configuration.md) | Every environment variable, with required, default, allowed values and effect |
| [Running in production](running.md) | Bind address, reverse proxy, health check, webhook token, upstream auth |
| [Monitoring](monitoring.md) | The `/health` endpoint, logs, and what is never logged |
| [Troubleshooting](troubleshooting.md) | Common errors and how to fix them |
| [Known limits](known-limits.md) | Caps and gaps you should know about before going live |
| [Backup and restore](backup-restore.md) | Why there is nothing to back up, and what happens on restart |
| [Upgrade](upgrade.md) | Updating the service and the vendored schemas |
| [Hosting the demo](demo-hosting.md) | Lab runbook: run the demo for an audience on the tailnet |

Quick facts:

- **Roles and permissions:** the service has none. It has no user accounts and does not authenticate callers.
  The only protected route is the APDS webhook, and only when `LINK_WEBHOOK_TOKEN` is set. Control who can
  reach the service at the network level (see [Running in production](running.md)).
- **State:** in memory only. Restarting the service loses the link registry; it is rebuilt from upstream
  on the next request.
- **Status:** proposal v0.1, a reference implementation. It has not been load-tested or hardened for public
  exposure.

The endpoint contract is in [docs/03-link-service.md](../03-link-service.md). Engineers should read the
[developer guide](../developer/README.md).

These pages describe the code as it is today (v0.1, written 2026-11-03). Draft PRs #3 to #6 are not merged
yet. Where they would change behaviour, the pages say so in a "Pending changes" note.
