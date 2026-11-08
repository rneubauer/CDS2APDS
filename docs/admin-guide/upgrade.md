# Upgrade

## Upgrading the service

There are no released packages yet; you upgrade from git. The service holds no persistent state, so there is
no data migration.

1. Read the changes since your version (the commit log, or the changelog once it exists). Look for new or
   changed environment variables.
2. Update the checkout:
   ```bash
   cd /opt/CDS2APDS
   git pull
   ```
3. Reinstall:
   - Python: `cd services/python && .venv/bin/pip install .`
   - TypeScript: `cd services/typescript && npm ci && npm run build`
4. Update your environment file if the variables changed (compare with [`.env.example`](../../.env.example)
   and [Configuration](configuration.md)).
5. Restart the service. The registry starts empty and fills on the next sync.
6. Warm it and check it:
   ```bash
   curl -fsS -X POST http://127.0.0.1:8080/sync > /dev/null
   curl -s http://127.0.0.1:8080/health
   ```

To roll back, check out the previous commit or tag and repeat steps 3 to 6.

## Updating the vendored schemas

`vendor/` holds pinned, unmodified copies of the CDS 1.1 and APDS 4.1 schemas
([ADR 0004](../decisions/0004-vendor-pinned-schemas.md)). Only `tools/validate_examples.py` uses them; the
running services do not read `vendor/`, so a schema update never needs a service restart.

Follow [vendor/README.md](../../vendor/README.md):

1. Replace the contents of `vendor/apds-4.1/` or `vendor/cds-1.1/` with a newer upstream copy. Do not edit the
   files by hand.
2. Update the commit hashes in the table in `vendor/README.md`.
3. Run the validator:
   ```bash
   pip install pyyaml jsonschema
   python tools/validate_examples.py
   ```
4. Read the `NOTE` lines. Each is an upstream defect patched in memory (`APDS_PATCHES`, `CDS_PATCHES` in the
   validator; listed in [profile §2.9](../02-link-profile.md#29-upstream-schema-issues-found)). If upstream has
   fixed one, remove its patch and update profile §2.9 in the same PR.
5. Fix any example that now fails, then run both service test suites, since the conformance fixtures reuse
   the examples.
6. Open a PR with the vendor update, the README hashes, and any example or profile changes together.

A new **major** version of either standard (for example APDS 5) is not a routine update: the profile,
the services and the examples may all need changes. Treat it as a design change and record it in
`docs/decisions/`.
