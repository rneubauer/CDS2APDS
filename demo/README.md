# Civic District demo

A one-command, fully offline demo of the three touchpoints, built on the
[Python reference link service](../services/python). The service runs unchanged; its CDS and
APDS upstreams are the in-memory fake that the conformance tests use
([`services/python/tests/fake_upstream.py`](../services/python/tests/fake_upstream.py)), loaded with
the fictional "Civic District" from [`examples/`](../examples) via
[`conformance/fixtures.json`](../conformance/fixtures.json).

## Run

From the repository root (Python 3.11+):

```bash
pip install -e services/python
python demo/server.py              # then open http://127.0.0.1:8742/demo/
python demo/server.py --port 8100  # another port
```

No network access is needed at runtime: no CDN scripts, web fonts or map tiles. The server binds
to 127.0.0.1 only and syncs the registry on startup. All service routes (`/health`, `/sync`,
`/links`, `/issues`, `/zones/{id}/off-street`, `/permits/verify`, `/webhooks/apds`) behave exactly as in
[docs/03](../docs/03-link-service.md). The demo adds `/demo/` (the page) and `/demo/upstream.json`
(zone geometry and place points for the map; assigned rights are left out, so no credential reaches
the browser).

Smoke test, so the demo can't break silently: `pip install -e "services/python[dev]"` then `pytest demo`.

## What's on the page

| Panel | Live call | Shows |
|---|---|---|
| Map | `GET /links` + `/demo/upstream.json` | Curb zones (orange), the curb area (dashed), APDS places (blue dots) and the entrance (blue square), with T1, T2 and T3 links drawn between them. Click a zone to select it |
| T1 access | `GET /links?cds_id={zone}` | Access links for the selected zone and whether they are confirmed on both sides |
| T2 nearby supply | `GET /zones/{zone}/off-street?radius_m=` | Nearby places: linked first, distance, free/total spaces. The search radius is drawn on the map |
| T3 shared permit | `POST /permits/verify` | The decision, the masked credential and the programme |
| Registry health | `GET /health`, `GET /links`, `GET /issues`, `POST /sync` | Every link with its status, and any issues |

Every panel has a **Raw JSON** toggle showing the exact request and response.

Demo data:

| What | Value |
|---|---|
| Garage entry apron (T1) | zone `…b001`, "Main St - Civic Garage entry apron" |
| Full metered block (T2) | zone `…b002`, "Main St 1100 block - metered": CDS says 0 of 8 spaces free |
| Resident permit zone (T3) | zone `…b003`, "Oak St 200 block - Zone A resident permit" |
| Valid credential | permit `ZA-004217`, or plate `EXM1234` (type `licensePlate`). Valid 2026-01-01 to 2026-12-31 |
| Invalid credential | `ZA-999999` (`not_found`); `ZA-004217` checked at `2027-02-01T00:00:00Z` gives `expired` |

## Five-minute talk track

**0:00 The problem (45 s).** Cities publish the curb in CDS (Open Mobility Foundation). Garage
operators publish facilities in APDS. Two standards, two communities, both work on their own. But a
driver at a full curb, or a parking officer checking a permit, needs both. Today that means custom
integrations for every city. We don't propose merging the standards. We link them at the three
places where the curb meets the garage. *Point at the three step buttons: T1, T2, T3.*

**0:45 The map (30 s).** This is the Civic District, fictional data that validates against both
official schemas. Orange is CDS: three curb zones in one curb area. Blue is APDS: the Civic Garage,
its Main St entrance, and two other lots. The coloured lines are the links the service found.
*Point out:* **no schema changes.** Every link sits in a field that already exists: CDS
`external_references`, APDS `operatorDefinedReference`.

**1:15 T1 access (60 s).** *Click "T1 Access" (or the small zone right under the garage).* This
no-stopping apron sits in front of the garage entrance. The CDS zone points to the APDS entrance,
and the entrance points back to the zone. Both sides declare it, so the link is **confirmed**. If only
one side declared it, it would show as one-sided, and the registry would flag a stale or broken
reference. *Open Raw JSON:* this is the plain `GET /links` answer, nothing more.

**2:15 T2 nearby supply (75 s).** *Click "T2 Nearby supply".* The metered block on Main St: CDS
says 0 of 8 spaces are free. Where do I send the driver? The service takes the zone centroid and asks
APDS with its standard radius search. The Civic Garage comes first because it is **linked**, with
119 of 420 spaces free, computed from APDS occupancy. *Change the radius to 2000 m:* East
Park-and-Ride appears, with capacity "unknown". It publishes no occupancy, and the service never
pretends a facility has space. *Point out the unit trap:* CDS `radius` is centimetres, APDS
`radius` is metres. The profile calls this out because it is an easy 100x mistake.

**3:30 T3 shared permit (75 s).** *Click "T3 Shared permit".* Oak St is a Zone A resident permit
zone. The CDS policy references an APDS RightSpecification, the same programme that is honoured in
the Civic Garage. An officer enters `ZA-004217`: **valid**. *Click "ZA-999999 (unknown)":*
**not found**. *Click "Plate EXM1234":* the same right, checked by licence plate. *Click
"ZA-004217 in Feb 2027":* **expired**, because the service checks issuance, expiry and the programme
window. *Point out privacy:* the credential travels in the request body, never in a URL. It comes back
masked (`ZA-***217`) and the service never logs it.

**4:45 Close (15 s).** *Scroll to Registry health.* Three links, no issues. One optional service, two
untouched standards, and a shared conformance suite that the Python and TypeScript services both pass.

## Likely questions

| Question | Short answer |
|---|---|
| Do CDS or APDS have to change? | No. Links use existing fields: CDS `external_references`, APDS `operatorDefinedReference`, and standard APDS queries ([README](../README.md), [01 §1.4](../docs/01-boundary.md#14-why-this-is-enough)) |
| Why not just put the garage into CDS, or the curb into APDS? | One source of truth per object: CDS for the curb, APDS for the facility. APDS *can* model on-street parking, but this profile doesn't use it for that ([01 §1.1](../docs/01-boundary.md#11-principle-linked-not-merged)) |
| Is the link service required? | No, it's optional. Everything works with the two standard APIs. The service adds a reverse index, one-sided and broken link detection, and one-call answers for T2 and T3 ([03](../docs/03-link-service.md)) |
| Why is the permit link "cds_only"? | APDS RightSpecification has no `operatorDefinedReference`, so permit links can only be declared on the CDS side. The service's registry provides the reverse lookup ([02 §2.5](../docs/02-link-profile.md#25-t3-shared-permits)) |
| What happens when a curb zone's geometry changes? | CDS issues a new zone id and lists the old one in `prev_curb_zone_ids`. The service re-points stale APDS references and reports `stale_cds_reference` ([02 §2.6](../docs/02-link-profile.md#26-identity-and-lifecycle)) |
| How does the service stay current? | APDS webhooks (`PlaceUpdated`, `RightSpecificationUpdated`, ...) for the off-street side. CDS has no change notifications, so it polls; `POST /sync` re-harvests both ([02 §2.7](../docs/02-link-profile.md#27-change-notification)) |
| Does it track vehicles from curb to garage? | No. No session hand-off: that would mean tracking individual vehicles. Rates are not translated either ([01 §1.3](../docs/01-boundary.md#13-explicit-non-goals)) |
| What about personal data? | Plates and permit numbers go to APDS only to answer a check, are masked in responses and are never logged ([02 §2.5](../docs/02-link-profile.md#25-t3-shared-permits), [03 §3.5](../docs/03-link-service.md#35-security-and-privacy)) |
| What does "unknown" capacity mean? | APDS publishes no occupancy for that place. Consumers must not assume it has space ([02 §2.4](../docs/02-link-profile.md#24-t2-nearby-off-street-supply-no-link-required)) |
| Did you find problems in the specs? | Yes, three schema issues, listed in [02 §2.9](../docs/02-link-profile.md#29-upstream-schema-issues-found) (for example, CDS `geoJSON_polygon` doesn't match RFC 7946). Candidates to report upstream |
| Is this endorsed by OMF or APDS? | Not yet. It's proposal v0.1 |

## Presenter notes

- The permit check uses the current time unless "Check at" is filled. `ZA-004217` is valid until
  2026-12-31T23:59:59Z. After that date, type `2026-06-01T12:00:00Z` into "Check at" to show a valid result.
- The "ZA-004217 in Feb 2027" chip fills "Check at", and that value stays for later checks. Click
  "ZA-004217 (valid)" to clear it again.
- The map is schematic. The entrance is about a metre from its curb zone, so the T1 link is drawn as a
  ring rather than a line. On a phone, secondary map labels are hidden; the laptop view reads best.
