# 0001. Link CDS and APDS at three touchpoints instead of merging them

Status: accepted (v0.1)

## Context
CDS 1.1 (OMF) models the public curb; APDS 4.1 models facilities. They overlap only where a curb meets
a facility. A merged model would need changes to both standards and two standards bodies to agree.

## Decision
Keep both domains fully usable on their own and connect them only at three touchpoints:
T1 access (Curb Zone ↔ `VehicularAccess`), T2 nearby supply (Curb Area/Zone ↔ `Place`), and
T3 shared permits (Curb Policy → `RightSpecification`). See `docs/01-boundary.md`.

## Consequences
No upstream schema changes are needed. Consumers that know only one standard are unaffected.
Anything outside the three touchpoints stays out of scope (see `docs/01-boundary.md`).
