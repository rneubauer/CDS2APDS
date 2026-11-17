---
title: "Merge plan for the open draft PRs"
audience: staff
product: CDS2APDS
status: current
reviewed: 2026-11-16
source: "Markdown copy of the review map published for Rick (https://claude.ai/artifact/1QGcWK1WStcgsbzaMqtmat, private; republished on Rick's current account 2026-11-17), state of 2026-11-16"
---

# Merge plan for the open draft PRs

All PRs below are drafts; none is merged and none has been reviewed yet (2026-11-16). Rick reviews and merges; the
order matters because most PRs are stacked. The live, phone-friendly version is the review map linked in the front
matter.

## Order

1. **#1** handoff files, decision records, CI on the lab runner. Merge first so CI checks everything after it.
2. **#3 → #4 → #5 → #6 → #11** service fixes, stacked. #3 matters most: the Python service logs permit and plate
   numbers until it merges. Together they are link-service API 0.2.0.
3. **#8 → #9, #10, #16** documentation (#8 is stacked on #1). This PR is stacked on #16.
4. **#2, #7, #13** independent: upstream bug-report draft, offline demo, MIT licence + Dependabot.
5. **Rick's decision first:** #12 with #15 together, and #14 (see below).

## PRs

| PR | What | Waits on |
|---|---|---|
| #1 | AGENTS.md, CLAUDE.md, `.env.example`, ADRs 0001–0004, CI | review |
| #2 | Links the APDS bug report, drafts the CDS one | review; filing upstream is Rick's call |
| #3 | Never log permit credentials; never follow upstream redirects | review |
| #4 | Python tolerates malformed upstream data; always answers with the envelope | #3 |
| #5 | Same input validation in both services | #4 |
| #6 | Last parity gaps; malformed permit status fails closed | #5 |
| #7 | Offline Civic District demo, its user guide and screenshots | review |
| #8 | User, admin, developer and API guides, changelog, docs CI | #1 |
| #9 | Runbook for hosting the demo on the tailnet | #8 |
| #10 | READMEs for conformance/, examples/, tools/ | #8 |
| #11 | Both services reject malformed base URLs the same way | #6 |
| #12 | Read CDS curb spaces so links to them resolve (API 0.3.0) | Rick's decision, with #15 |
| #13 | MIT licence and weekly Dependabot | Rick confirms the copyright holder |
| #14 | Webhooks fail closed without a token | Rick's decision (breaking for operators) |
| #15 | Link kinds follow the profile §2.1 table exactly | Rick's decision, with #12 |
| #16 | Front matter on every doc; public vs internal split (nothing public) | #8 |

## Known merge follow-ups

- Whichever of #6 and #8 merges last bumps the API version to 0.2.0 (FastAPI `version`, `package.json`) and
  regenerates `docs/api/openapi.json`.
- #3 needs a `Docs: none` line once #8's docs check is on `main`.
- #9 and #10 both change the docs-backlog count line; #10 and #16 touch the same two files' tops.
- #1 and #14 both add `.env.example`; keep both sets of names.
- If Rick takes #12: then a profile §2.1 change adding Curb Space only where APDS has a counterpart, with a profile
  version bump; then #15 updated to match (Lab-Architecture's recommendation).
