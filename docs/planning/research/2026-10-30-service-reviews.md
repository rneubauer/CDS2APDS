---
title: "Security and parity reviews of the link services"
audience: staff
product: CDS2APDS
status: current
reviewed: 2026-11-16
source: "Read-only reviews run 2026-10-30, plus review notes from the docs work (2026-11-03) and Lab-Architecture (2026-11-05/06)"
---

# Security and parity reviews of the link services

Two read-only reviews of `services/python` and `services/typescript` on `main` (commit 935cdd1), run in parallel on
2026-10-30: a security review and a Python/TypeScript parity review against docs/03. Each finding was checked by hand
before it was fixed. This page records what was found and where it went.

## Security review

| Severity | Finding | Status |
|---|---|---|
| HIGH | Python logged permit and plate numbers in clear text: httpx logs each request URL at INFO, and the permit lookup carries `credential_id` in the query (reproduced) | Fixed in #3 |
| MEDIUM | TypeScript followed upstream redirects, which would forward the credential query and `X-MCC-Access-Token` to another host | Fixed in #3 |
| LOW | Ids `.` and `..` aren't encoded, so URL normalisation sent `/curbs/zones/..` upstream as `/curbs` | Fixed in #5 |
| LOW | Webhook endpoint open when `LINK_WEBHOOK_TOKEN` is unset | Option in #14 (Rick decides) |
| LOW | No cap on upstream response size | Open; noted here |
| — | Checked and fine: constant-time token compare in both; credentials masked in responses; request body limit 1 MiB in both; no SSRF via payload links | — |

## Parity review (things the conformance suite didn't catch)

| Finding | Fixed in |
|---|---|
| Python returned FastAPI's own 404/405 bodies and a plain-text 500 instead of the envelope | #4 |
| Python crashed on malformed upstream data; one bad webhook made `/links` fail until the next `/sync` | #4 |
| `at` of `2026-02-30` accepted by TypeScript (rolled over); `0001-01-01T00:00:00+05:00` was a 500 in Python | #5 |
| Repeated query parameters: 400 in TypeScript, last value used in Python | #5 |
| Fractional seconds: microseconds vs milliseconds | #5 |
| className `"constructor"` accepted by TypeScript; non-string values coerced differently; sort tie-breaks differed | #6 |
| Malformed base URLs (`http:foo`, `http://:80`) accepted by one side | #11 |
| `420.0` as a count; badly formed `reference_url`; ids with emoji sort order | Open: spec questions for Rick (recommended: accept 420.0, reject the URL, sort by code point) |

## Found while writing the docs (2026-11-03)

- The service never read CDS curb spaces, although docs/03 lists them as link ends → option in #12.
- The service accepted more link types than the profile §2.1 table allows → option in #15.

## Architecture review notes (Lab-Architecture, recommendations only)

- #6: a present but non-string `validityStatus` must fail closed (fixed, commit 306c1e7).
- #12: prove only a 404 on optional endpoints means "none" (tests added, commit 39613fc); version it as 0.3.0.
- #14: keep the insecure flag for local use only; bump the minor version; tell operators in the changelog.
- #12 + #15: decide together; add Curb Space to the profile only where APDS has a counterpart.
