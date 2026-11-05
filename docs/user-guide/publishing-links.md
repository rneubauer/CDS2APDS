# Publishing links

A link says "this curb record and this parking record belong together". You add it to data you already publish.
No schema changes are needed. All ids below are from the fictional examples in [`examples/`](../../examples).

## Which link do I need?

| You want to say… | Link kind | CDS record | APDS record |
|---|---|---|---|
| "This garage entrance is on this curb zone" | access (T1) | Curb Zone | VehicularAccess element |
| "When this curb is full, send drivers to this garage" | supply (T2) | Curb Area or Curb Zone | Place element |
| "This curb permit is also valid in these garages" | permit (T3) | Curb Policy | RightSpecification |

A link can be declared on one side only. Declaring it on both sides makes it **confirmed**, which lets consumers
spot stale data. Permit links can only be declared on the CDS side.

## In CDS: add an external reference

1. Open the CDS object (Curb Zone, Curb Area or Curb Policy) in your curb data system.
2. Add an entry to its `external_references` list:

   | Field | Value |
   |---|---|
   | `name` | `APDS` |
   | `reference_url` | The full URL of the one APDS record, for example `https://apds.example.org/v4/places/7d41e6b2-8c3f-4a9d-b210-00000000f002`. For a permit, use `…/rights/specs/{id}` |
   | `identifier_name` | `HierarchyElement.id`, or `RightSpecification.id` for a permit |
   | `ids` | The APDS id from the URL, as a one-item list |

3. Publish as usual. Adding a link does **not** give the zone a new `curb_zone_id`.

Example: [`curb_zone.garage-driveway.json`](../../examples/cds/curb_zone.garage-driveway.json).

## In APDS: set operatorDefinedReference

1. Open the APDS element: the VehicularAccess (entrance) for an access link, or the Place for a supply link.
2. Set `operatorDefinedReference` to:

   | Field | Value |
   |---|---|
   | `id` | The CDS id, for example the `curb_zone_id` |
   | `className` | `CdsCurbZone`, `CdsCurbArea`, `CdsCurbSpace` or `CdsCurbObject` (exactly these spellings) |
   | `version` | `1` (always) |

3. Publish as usual.

Example: [`vehicular-access.main-st-entry.json`](../../examples/apds/vehicular-access.main-st-entry.json).

## Common questions

**A garage has several entrances.** Set `operatorDefinedReference` on each entrance. That is the normal case.

**A garage should be linked to several curb areas.** An APDS element holds one reference. Declare the extra links
on the CDS side only.

**We already use operatorDefinedReference for something else.** Keep using it. Declare the links on the CDS side only.

**A curb zone's geometry changed and it got a new id.** Update `operatorDefinedReference` on the APDS side to the new
`curb_zone_id`. Consumers can follow `prev_curb_zone_ids` in the meantime.

**A curb zone was retired.** Remove the links that point to it.

**Is it safe to link permits?** Yes. The link only names the permit programme. Plates and permit numbers are
never part of a link.

## Check your data

Validate your payloads against the official schemas the same way the examples are checked:
`python tools/validate_examples.py` (see the [developer guide](../developer/README.md) for adding your own files).

Rules in full: [link profile §2.1–2.3, §2.5, §2.6](../02-link-profile.md).
