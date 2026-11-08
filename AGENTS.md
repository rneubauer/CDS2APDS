# AGENTS.md

Handoff notes for anyone (human or agent) picking up this repository.

## What this is

A proposal for linking on-street curb data (OMF **CDS 1.1**) with off-street parking data (**APDS 4.1**)
without merging the two standards. It has three parts that must stay in step:

1. **The profile** (`docs/02-link-profile.md`) is normative. Code follows the profile, not the other way round.
2. **Examples** (`examples/`) are validated against the vendored upstream schemas in `vendor/`.
3. **Two reference services** (`services/python`, `services/typescript`) that must behave identically.
   Both run the shared, language-neutral suite in `conformance/`.

## Checks (all must pass before a PR)

```bash
python tools/validate_examples.py                               # needs: pip install pyyaml jsonschema
cd services/python && pip install -e ".[dev]" && pytest --cov   # Python 3.11+
cd services/typescript && npm ci && npm test && npm run build   # Node 20+
```

CI (`.github/workflows/ci.yml`) runs the same three steps on the lab runner `umo-lab-app01-cds2apds`
(`runs-on: [self-hosted, cds2apds]`; approved by Rick 2026-11-08). The runner takes one job at a time and offers no
Actions cache or artifact upload, so workflows must not use `actions/cache`, `cache:` options or `upload-artifact`.

## Rules of the road

- **Behaviour changes go into `conformance/` first**, then into both services. Never change one service alone.
- **Do not edit `vendor/`.** Upstream schema bugs are patched in memory by `tools/validate_examples.py`
  and listed in profile §2.9. To update a vendored spec, follow `vendor/README.md`.
- **Configuration** comes only from environment variables (`.env.example` lists the names; meanings in
  `docs/03-link-service.md` §3.1). No secrets in the repo.
- **Privacy:** licence plates and permit numbers are personal data. Never log them in clear text or echo
  them in responses (profile §2.5).
- Record design decisions in `docs/decisions/` (one numbered file each).
- **Docs are part of every change** (lab documentation standard, 2026-11-03). A PR that changes behaviour, settings,
  the API or a screen updates the matching page in `docs/user-guide`, `docs/admin-guide`, `docs/developer` or
  `docs/api`, plus `CHANGELOG.md`, and lists the doc changes in its description. If no docs change, the PR body
  says why on a line starting `Docs: none`. CI checks this (`.github/workflows/docs.yml`). Never put secrets or
  real personal data in docs.
- `docs/cds-apds-link-profile.html` is a standalone rendering of the profile for sharing; keep it in sync
  when the profile text changes.
