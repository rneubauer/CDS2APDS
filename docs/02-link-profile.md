# 2. CDS–APDS Link Profile v0.1

**Status:** Proposal · **Applies to:** CDS 1.1.0, APDS 4.1

The key words MUST, SHOULD and MAY are used as in RFC 2119. All examples live in
[`../examples`](../examples) and validate against the official schemas
(`python tools/validate_examples.py`).

## 2.1 Link model

A **link** joins exactly one CDS record to exactly one APDS record:

| Link kind | CDS record | APDS record | Declared in CDS | Declared in APDS |
|---|---|---|---|---|
| `access` | Curb Zone, Curb Object | HierarchyElement with `type: vehicularAccess` | `external_references` (§2.2) | `operatorDefinedReference` (§2.3) |
| `supply` | Curb Area, Curb Zone | HierarchyElement with `type: place` (or `campus`) | `external_references` (§2.2) | `operatorDefinedReference` (§2.3) |
| `permit` | Curb Policy | RightSpecification | `external_references` (§2.2) | none; see §2.5 |

A link is **confirmed** when it is declared on both sides, and **one-sided** when it is declared on
only one. One-sided links are valid; confirmation just lets consumers detect stale data.

## 2.2 CDS → APDS: `external_references`

A CDS publisher declares a link by adding an [External Reference](https://github.com/openmobilityfoundation/curb-data-specification/blob/main/data-types.md#external-reference)
to the CDS object:

| Field | Value | Rule |
|---|---|---|
| `name` | `"APDS"` | MUST be exactly `APDS` (consumers SHOULD compare case-insensitively) |
| `reference_url` | Full HTTPS URL of the APDS **resource**: `{apds-base}/places/{id}` for access and supply, `{apds-base}/rights/specs/{id}` for permit | MUST point to a single resource, not a list query |
| `identifier_name` | `"HierarchyElement.id"` or `"RightSpecification.id"` | SHOULD be present |
| `ids` | `["{id}"]` | SHOULD contain exactly the id in the URL. If present, it takes precedence over the URL |
| `public` | `false` unless the APDS endpoint is open | MAY be present |

```json
"external_references": [{
  "name": "APDS",
  "reference_url": "https://apds.example.org/v4/places/7d41e6b2-8c3f-4a9d-b210-00000000f002",
  "public": false,
  "identifier_name": "HierarchyElement.id",
  "ids": ["7d41e6b2-8c3f-4a9d-b210-00000000f002"]
}]
```

The link kind is not written anywhere. Consumers derive it from the two ends: a Curb Policy
pointing at `/rights/specs/` is `permit`; anything pointing at a `vehicularAccess` element is
`access`; anything pointing at a `place` or `campus` is `supply`.

`external_references` does not change a Curb Zone's identity, so adding, changing or removing a link
**MUST NOT** trigger a new `curb_zone_id` (CDS 1.1 already states this).

## 2.3 APDS → CDS: `operatorDefinedReference`

An APDS publisher declares a link by setting `operatorDefinedReference` (a `VersionedReference`)
on the HierarchyElement:

| Field | Value | Rule |
|---|---|---|
| `id` | The CDS UUID (`curb_zone_id`, `curb_area_id`, `curb_space_id` or `curb_object_id`) | MUST |
| `className` | `CdsCurbZone`, `CdsCurbArea`, `CdsCurbSpace` or `CdsCurbObject` | MUST. APDS requires `^[A-Z]+[A-Za-z0-9]+`, so values like `cds:CurbZone` are **invalid** |
| `version` | `1` | MUST be `1`. CDS objects are not versioned; the CDS id is the stable key (§2.6) |

```json
"operatorDefinedReference": { "id": "3f2a9c1e-5b7d-4e8a-9c01-00000000b001", "version": 1, "className": "CdsCurbZone" }
```

**One reference per element.** `operatorDefinedReference` holds a single value, so:

- A facility with several entrances declares one `access` link on **each** VehicularAccess
  element. This is the normal case and needs no workaround.
- A Place links to at most one Curb Area (or Zone). If a Place must be linked to several
  CDS areas, declare the extra links on the CDS side only; they are valid one-sided links.
- Implementers **MUST NOT** use `operatorDefinedReference` for CDS links if they already use it for
  their own internal reference. In that case the CDS side declares the link alone.

## 2.4 T2: nearby off-street supply (no link required)

Nearby supply works **without any declared link**: a CDS consumer takes a point on the curb
(for example the centroid of the Curb Zone) and calls APDS natively:

```
GET {apds-base}/places?latitude={lat}&longitude={lng}&radius={metres}&type=place&expand=occupancy,pointLocation,characteristics
```

Declared `supply` links (§2.1) are a *preference* signal: linked Places SHOULD be shown before
Places that only match the radius search.

**Unit trap:** CDS `radius` is in **centimetres**; APDS `radius` is in **metres**.

Available capacity is derived from APDS fields, most specific first:

1. `supplyQuantity` (with `supplyViewType: spaceView`) minus the latest `demandType[].count`
2. otherwise `round(supplyQuantity × (1 − percentage / 100))`
3. otherwise unknown (`null`); consumers MUST NOT assume a facility is available

## 2.5 T3: shared permits

**Declaring the programme.** A CDS Policy whose Rule restricts use to permit holders
(`"permit"` in `user_classes` and/or `purposes`) MAY carry an APDS `external_reference` to the
`RightSpecification` that defines the permit programme (`type: permitParking`). The APDS
RightSpecification's `hierarchyElements` lists the facilities where the same permit is honoured.

```json
"rules": [{ "activity": "parking", "user_classes": ["permit"], "purposes": ["permit"] }],
"external_references": [{
  "name": "APDS",
  "reference_url": "https://apds.example.org/v4/rights/specs/7d41e6b2-8c3f-4a9d-b210-00000000f101",
  "identifier_name": "RightSpecification.id",
  "ids": ["7d41e6b2-8c3f-4a9d-b210-00000000f101"]
}]
```

**Verifying a vehicle.** CDS enforcement already knows the curb zone and has a
`vehicle_permit_number` and/or `vehicle_license_plate`. It asks APDS natively:

```
GET {apds-base}/rights/assigned?right_spec={rightSpecId}&credential_id={permit-or-plate}&credential_type=permit,licensePlate
```

A permit is **valid at instant _t_** when all of the following hold:

1. an AssignedRight is returned whose `rightSpecification.id` is one of the linked programmes;
2. one of its `rightHolder.credentials[].identifier.id` equals the presented credential
   (compare case-insensitively, ignoring spaces and hyphens);
3. `issuanceTime` ≤ _t_ (if present) and _t_ < `expiry` (if present);
4. the RightSpecification's `validity.validityStatus` is not `suspended` or `planned`, and _t_ lies
   within `validityTimeSpecification.overallStartTime` / `overallEndTime`.

Whether the **CDS Policy itself applies** at _t_ (time spans, priority) is still decided by the CDS
consumer, as it is today. This profile only answers "does this vehicle hold the permit?".

**No APDS back-reference.** RightSpecification has no `operatorDefinedReference`, so permit links
are declared on the CDS side only. A reverse lookup ("which curb policies honour this
programme?") needs an index, which the reference link service provides ([03-link-service.md](03-link-service.md)).

**Privacy.** Plates and permit numbers are personal data in many jurisdictions. Implementations
SHOULD send them to APDS only to answer a verification request, MUST NOT log them in clear text,
and SHOULD NOT echo them in responses.

## 2.6 Identity and lifecycle

| Event | CDS behaviour | APDS behaviour | Effect on links |
|---|---|---|---|
| Metadata change | Same `curb_zone_id`, new `last_updated_date` | Same `id`, `version` + 1 | None |
| Geometry change | **New** `curb_zone_id`; old id listed in `prev_curb_zone_ids` | Same `id`, `version` + 1 | APDS references to the old zone id become stale. Consumers SHOULD resolve them through `prev_curb_zone_ids`, and APDS publishers SHOULD update `operatorDefinedReference` |
| Retirement | Zone gets `end_date`; returned only with `show_historic` | Logical delete (`DeletedReference` in `modified_since` listings; `PlaceDeleted` webhook) | Link becomes broken and SHOULD be removed |

APDS references to CDS use `version: 1` permanently, and CDS references to APDS carry no
version, so both always resolve to the **latest** counterpart record.

## 2.7 Change notification

- **APDS → consumers:** subscribe with `POST {apds-base}/webhooks`, topics `PlaceCreated`,
  `PlaceUpdated`, `PlaceDeleted`, `RightSpecificationUpdated` and `RightSpecificationDeleted`. The
  payload is the changed record (`EventData`). APDS recommends a per-project header carrying the event
  type; this profile names it `X-APDS-Event-Type`.
- **CDS → consumers:** CDS has no change notifications. Poll `GET /curbs/zones`, `/curbs/areas`
  and `/curbs/policies` and compare `last_updated_date`.

## 2.8 Conformance

| Role | Requirements |
|---|---|
| **CDS publisher (link-aware)** | §2.2, plus §2.5 "Declaring the programme" when T3 is used |
| **APDS publisher (link-aware)** | §2.3; publishes `supply`/`demandTable` for T2 where available |
| **Consumer** | Derives link kind (§2.2), handles one-sided and stale links (§2.1, §2.6), converts radius units (§2.4), applies the validity rules and privacy rules (§2.5) |

## 2.9 Upstream schema issues found

These were found while validating the examples. `tools/validate_examples.py` patches them in memory
and prints them on every run.

| Spec | Location | Issue | Suggested fix |
|---|---|---|---|
| APDS 4.1 | `components/schemas/Reference` | `required: [id, className]` combined with `maxProperties: 1`: no instance can ever validate. This affects `CredentialAssigned.identifier`, `Segment.credentialId` and `DemandSpaceType.spaceId` | Remove `minProperties`/`maxProperties` |
| CDS 1.1 (cds-openapi) | `Shared Data Models/geoJSON_polygon.yaml` | `coordinates` is a single list of positions (LineString shape). RFC 7946 Polygons are arrays of linear rings, and the CDS prose spec requires RFC 7946 | `coordinates: {type: array, items: {$ref: ./coordinates.yaml}}` |
| CDS 1.1 (cds-openapi) | `Shared Data Models/coordinates.yaml` | Description says positions are "latitude and longitude"; RFC 7946 order is **longitude, latitude** | Fix the description |
