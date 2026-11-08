# Build, run and test

Run all commands from the repository root unless a step says otherwise. CI
(`.github/workflows/ci.yml`) runs the same three checks on every push to `main` and every pull request.

## Prerequisites

| Tool | Version | Used by |
|---|---|---|
| Python | 3.11 or newer (CI uses 3.11, 3.12 and 3.13) | Python service, example validator |
| Node.js and npm | Node 20 or newer (CI uses 20 and 22) | TypeScript service |
| git | any recent | everything |

## 1. Example validator

1. Install the two libraries it needs:
   ```bash
   pip install pyyaml jsonschema
   ```
2. Run it:
   ```bash
   python tools/validate_examples.py
   ```
3. Expect two `NOTE` lines (the in-memory upstream schema fixes), one `ok` line per example, and
   `14/14 examples valid`. Exit code 0 means all examples are valid.

## 2. Python service

1. Create a virtual environment and install the package with test extras:
   ```bash
   cd services/python
   python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
   pip install -e ".[dev]"
   ```
2. Run the tests (conformance suite plus unit tests) with coverage:
   ```bash
   pytest --cov
   ```
   CI also enforces `--cov-fail-under=80`.
3. Run the service against real or test upstreams:
   ```bash
   export CDS_BASE_URL=https://cds.example.org
   export APDS_BASE_URL=https://apds.example.org/v4
   python -m cds_apds_link          # or: cds-apds-link
   ```
4. Check it: `curl http://localhost:8080/health`.

## 3. TypeScript service

1. Install dependencies from the lock file:
   ```bash
   cd services/typescript
   npm ci
   ```
2. Check types, run the tests, and build:
   ```bash
   npm run typecheck
   npm test              # conformance suite plus unit tests
   npm run coverage      # optional: tests with a v8 coverage report
   npm run build         # compiles src/ to dist/
   ```
3. Run the built service:
   ```bash
   export CDS_BASE_URL=https://cds.example.org
   export APDS_BASE_URL=https://apds.example.org/v4
   npm start
   ```
4. Check it: `curl http://localhost:8080/health`.

All environment variables are listed in the [admin guide configuration page](../admin-guide/configuration.md).

## Adding a conformance case

The rules come from [AGENTS.md](../../AGENTS.md) and [ADR 0003](../decisions/0003-two-reference-services.md):

- **Behaviour changes go into `conformance/` first**, then into both services. Never change one service alone.
- The profile is normative. If a change affects publishers or consumers, update
  [docs/02-link-profile.md](../02-link-profile.md) (and `docs/cds-apds-link-profile.html`) too.
- Update the service contract in [docs/03-link-service.md](../03-link-service.md) when an endpoint,
  field, error or variable changes.
- Do not edit `vendor/`.

Steps:

1. **Describe the behaviour.** Write or update the rule in `docs/03-link-service.md` (and the profile if needed).
2. **Add test data if you need it.**
   1. Add the payload to `examples/cds/` or `examples/apds/`.
   2. Add an entry for it to `examples/manifest.json` and run `python tools/validate_examples.py`.
   3. List it in the right array in `conformance/fixtures.json` (`cds.zones`, `cds.areas`, `cds.policies`,
      `apds.elements`, `apds.right_specs` or `apds.assigned_rights`).
   4. Adding fixtures changes what every case sees (for example the link list from `POST /sync`).
      Update existing cases that list all links or issues.
3. **If the fake upstream must behave differently** (a new route or query parameter), change the rule text
   in `fixtures.json` under `fake_upstream`, and change **both** `services/python/tests/fake_upstream.py` and
   `services/typescript/test/fake-upstream.ts` the same way.
4. **Add the case** to `conformance/cases.json`: a `name` and a list of `steps`, each with a `request` and an
   `expect` (see the [code map](code-map.md#casesjson) for the format). Keep `expect.body` to the fields the
   case is about; the match is a subset match. Remember the clock is fixed at `2026-06-01T12:00:00Z`.
5. **Run both suites and watch the new case fail** (`pytest` and `npm test`).
6. **Change both services** until both suites pass. Keep module names and structure parallel
   (`registry.py` and `registry.ts`, and so on), so the next person can compare them line by line.
7. **Run all three checks** from [AGENTS.md](../../AGENTS.md) before opening the PR.
8. **Update the docs** in the same PR: this guide, the admin guide if configuration or limits change, and the
   contract.

Tests that only one implementation needs (for example a Python-only edge case in the HTTP layer) go in
`test_units.py` or `units.test.ts`. Behaviour a client can see belongs in the shared suite.

## Keeping the HTML page in sync

`docs/cds-apds-link-profile.html` is a standalone copy of the profile for sharing. It is written by hand.
When you change [docs/02-link-profile.md](../02-link-profile.md), update the HTML page by hand in the same PR.
Nothing checks this: no CI job compares the two files, so a reviewer has to look.

## Conventions

- Configuration comes only from environment variables. No secrets in the repo; `.env` is git-ignored.
- Licence plates and permit numbers are personal data. Never log them in clear text and never echo them in
  responses (profile §2.5). Credentials go in request bodies, never in URLs of this service.
- Upstream responses are untrusted. A malformed response must become `502 upstream_error`, not a crash.
- Commit messages use conventional types (`feat:`, `fix:`, `docs:`, ...).
- Record design decisions in `docs/decisions/`, one numbered file each.
