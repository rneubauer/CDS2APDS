# Tools

Small Python scripts for checks and generated files. Run them from the repository root. Each one exits
non-zero when it finds a problem.

| Script | Purpose | Run | CI |
|---|---|---|---|
| `validate_examples.py` | Validates every payload listed in `examples/manifest.json` against the vendored CDS 1.1 and APDS 4.1 schemas. Patches known upstream schema defects in memory and prints a `NOTE` for each | `pip install pyyaml jsonschema`, then `python tools/validate_examples.py` | `ci.yml`, job `examples` |
| `check_links.py` | Checks that every relative link and `#anchor` in the tracked `*.md` files resolves. Offline: `http(s)` and `mailto` links are skipped. Links in code are ignored | `python tools/check_links.py` (all files) or `python tools/check_links.py a.md b.md` | `docs.yml`, job `links` |
| `gen_openapi.py` | Writes `docs/api/openapi.json` from the Python service. The file is generated; do not edit it by hand. With `--check` it only reports whether the committed file is stale | `pip install -e services/python`, then `python tools/gen_openapi.py` (or `--check`) | `docs.yml`, job `api-reference` (regenerates and fails on a `git diff`) |
| `check_docs_changed.py` | Fails a pull request that changes `services/*/src/`, `conformance/` or `.env.example` without changing something under `docs/` or `CHANGELOG.md`. A PR description line starting with `Docs: none` opts out | `python tools/check_docs_changed.py <base-sha> <head-sha>` (reads the PR description from `$GITHUB_EVENT_PATH`) | `docs.yml`, job `docs-changed` (pull requests only) |

Notes:

- `gen_openapi.py` builds the app with dummy settings and a transport that refuses every call, so it needs no
  network. The docs workflow pins `fastapi==0.162.0` and `pydantic==2.14.2`; if you bump them, regenerate
  `docs/api/openapi.json` in the same PR.
- `check_docs_changed.py` runs `git diff --name-only <base>...<head>`, so it needs full git history
  (`fetch-depth: 0`).
- No tool checks that `docs/cds-apds-link-profile.html` matches `docs/02-link-profile.md`; see
  [Keeping the HTML page in sync](../docs/developer/build-run-test.md#keeping-the-html-page-in-sync).
