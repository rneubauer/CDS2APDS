# Changelog

All notable changes to this project are listed here, in terms a user of the profile or the link
service would notice. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
versions follow the proposal's version number.

## [Unreleased]

Everything below is in open draft pull requests. **Nothing here has merged yet**: each entry is marked
*pending* with its PR number. PRs #3 to #6 are a stack and merge in that order.

### Added

- *Pending, #1:* Handoff files for new contributors (`AGENTS.md`, `CLAUDE.md`), a `.env.example` listing every
  setting by name, the first four design decision records in `docs/decisions/`, and CI that validates the
  examples and tests both services on every pull request.
- *Pending, #2:* A link to the APDS schema bug already reported upstream (parkingdata/spec#33) and a ready-to-file
  draft for the CDS Polygon `coordinates` bug. Nothing new has been filed upstream.
- *Pending, #7:* An offline demo of the three touchpoints (`python demo/server.py`): a map of the Civic District,
  nearby garages with availability, and a permit check. It runs on the example data, with no network needed.
- *Pending, #8:* An API reference in `docs/api/`: `openapi.json` generated from the Python service, plus a
  copy-paste `curl` example for every endpoint (tested in CI). This changelog. A docs workflow that checks
  relative links, keeps the API reference current, and asks for docs changes in PRs that change the services.
- *Pending, docs/folder-readmes:* READMEs for `conformance/` (case and fixture format), `examples/` (what each
  payload shows) and `tools/` (each script and the CI job that runs it), and a note on keeping the HTML profile
  page in sync.

### Changed

- *Pending, #4:* The Python service always answers with the `{success, data, error}` envelope, including for
  unknown routes (404 `not_found`) and unexpected failures (500 `internal_error`). FastAPI's built-in `/docs`,
  `/redoc` and `/openapi.json` pages are switched off.
- *Pending, #5:* Both services validate input the same way. Impossible dates such as `2026-02-30` are rejected,
  fractional seconds are cut to milliseconds, a repeated query parameter is rejected, and the ids `.` and `..`
  are treated as not found.
- *Pending, #6:* The last differences between the Python and TypeScript services are removed. Unexpected
  non-text values from upstream count as absent in both, and ties in sort order break the same way.
  docs/03 now lists the `500 internal_error` response and the 404 for unknown routes.

### Fixed

- *Pending, #4:* One malformed `PlaceCreated` webhook could break `/links` and every later webhook in the Python
  service until the next `/sync`. Registry updates are now all-or-nothing. A malformed upstream reference is
  reported as an issue instead of crashing.
- *Pending, #6:* In the TypeScript service, an APDS `className` such as `constructor` no longer adds a false
  issue to `GET /issues`.

### Security

- *Pending, #3:* The Python service no longer writes permit numbers or licence plates to its log. Before this
  fix, the HTTP client logged the full upstream URL, including the credential. The TypeScript service no
  longer follows upstream redirects, so a credential or APDS token can't be sent to another host. Any
  non-2xx upstream answer is now reported as `upstream_error`.

## [0.1.0] - 2026-09-23

First version of the proposal (commit `935cdd1`).

### Added

- **Link profile** (`docs/02-link-profile.md`, normative): links on-street curb data (OMF CDS 1.1) with off-street
  parking data (APDS 4.1) at three touchpoints, without merging the standards or changing their schemas:
  T1 access (a garage entrance on a curb zone), T2 nearby off-street supply, and T3 shared permits.
  Every link uses fields that already exist: CDS `external_references` and APDS `operatorDefinedReference`.
- **Domain boundary** (`docs/01-boundary.md`): what overlaps between the two standards and what deliberately doesn't.
- **Worked examples** (`examples/`): a fictional "Civic District" with curb zones, policies, a garage, lots and a
  resident permit, validated against the vendored CDS 1.1 and APDS 4.1 schemas by `tools/validate_examples.py`.
- **Two reference link services**, Python (FastAPI) and TypeScript (Fastify), with the same HTTP API
  (`docs/03-link-service.md`): link registry and sync, link issues, nearby off-street supply for a curb zone,
  permit verification, and an APDS webhook receiver.
- **Conformance suite** (`conformance/`): language-neutral fixtures and test cases that both services must pass.
- **Vendored upstream schemas** (`vendor/`), pinned, with their licences. Upstream schema bugs found while
  validating are listed in profile §2.9.
- A standalone HTML rendering of the profile for sharing (`docs/cds-apds-link-profile.html`).

[Unreleased]: https://github.com/rneubauer/CDS2APDS/compare/935cdd1...HEAD
[0.1.0]: https://github.com/rneubauer/CDS2APDS/commit/935cdd1
