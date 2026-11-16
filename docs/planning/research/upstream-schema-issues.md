---
title: "Upstream schema issues and their reporting status"
audience: staff
product: CDS2APDS
status: current
reviewed: 2026-11-16
source: "Profile §2.9 (docs/02-link-profile.md), PR #2 drafts, upstream issue search 2026-10-27"
---

# Upstream schema issues and their reporting status

Found while validating the examples against the official schemas. The full table with suggested fixes is in
[profile §2.9](../../02-link-profile.md#29-upstream-schema-issues-found); `tools/validate_examples.py` patches them in
memory.

| Spec | Issue | Reported? |
|---|---|---|
| APDS 4.1 | `Reference` requires two properties but allows at most one, so no instance validates | Yes, by Rick: parkingdata/spec#33 |
| CDS 1.1 (cds-openapi) | Polygon `coordinates` has LineString shape, not RFC 7946 Polygon shape | No. Draft ready in PR #2; searched OMF repos 2026-10-27, no existing report |
| CDS 1.1 (cds-openapi) | `coordinates.yaml` says "latitude and longitude"; RFC 7946 is longitude, latitude | No. Folded into the same draft |

Filing on OMF's GitHub is outward-facing, so it needs Rick's OK. The vendored pins were still upstream HEAD on
2026-10-27, so the bugs were current then.
