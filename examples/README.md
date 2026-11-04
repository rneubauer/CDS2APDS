# Examples

Fictional data for a "Civic District": invented names, UUIDs and coordinates, no real operator. The payloads
show the three touchpoints of the [link profile](../docs/02-link-profile.md): **T1** access (a garage entrance
on a curb zone), **T2** nearby off-street supply, **T3** shared permits.

`manifest.json` lists every payload with its `spec` (`cds` or `apds`) and the `schema` it must validate against.
`python tools/validate_examples.py` reads it and checks each file against the vendored schemas in `vendor/`;
CI runs this in the `examples` job. The same files are the upstream data for
[`conformance/fixtures.json`](../conformance/README.md), except `curb_event.permit-check.json`, which the
fixtures do not list.

Adding a payload: put the file here, add an entry to `manifest.json`, run the validator. Add it to
`conformance/fixtures.json` only if the services should see it.

## CDS 1.1 (`cds/`)

Schemas are in `vendor/cds-1.1/Shared Data Models/`.

| File | What it is | Touchpoint | Validates against |
|---|---|---|---|
| `curb_area.civic-district.json` | The Civic District area (polygon) | T2 | `curb_area.yaml` |
| `curb_zone.garage-driveway.json` | No-stopping apron in front of the Civic Garage entrance | T1 | `curb_zone.yaml` |
| `curb_zone.metered.json` | Main St 1100 block, metered parking | T2 | `curb_zone.yaml` |
| `curb_zone.resident-permit.json` | Oak St 200 block, Zone A resident permit parking | T3 | `curb_zone.yaml` |
| `curb_policy.no-stopping.json` | Policy: no stopping (the garage apron) | T1 | `curb_policy.yaml` |
| `curb_policy.metered.json` | Policy: metered parking, 2 hour limit, with a rate | T2 | `curb_policy.yaml` |
| `curb_policy.resident-permit.json` | Policy: Zone A permit holders park without time limit; refers to the APDS permit programme | T3 | `curb_policy.yaml` |
| `curb_event.permit-check.json` | A `vehicle_detected` event in the permit zone, carrying `vehicle_permit_number` | T3 | `curb_event.yaml` |

## APDS 4.1 (`apds/`)

Schemas are components in `vendor/apds-4.1/apds-api-4.1.yaml`.

| File | What it is | Touchpoint | Validates against |
|---|---|---|---|
| `place.civic-garage.json` | The Civic Garage: 420 spaces, a demand table, a reference to the CDS curb area, and the Zone A right specification | T2, T3 | `Place` |
| `vehicular-access.main-st-entry.json` | The garage entrance on Main St (a `vehicularAccess` element, child of the garage) | T1 | `VehicularAccess` |
| `place.library-lot.json` | Library Surface Lot: 80 spaces, occupancy given as a percentage | T2 | `Place` |
| `place.east-lot.json` | East Park-and-Ride: has no `supply` figure | T2 | `Place` |
| `right-spec.zone-a-permit.json` | Right specification of type `permitParking`: the Zone A permit programme | T3 | `RightSpecification` |
| `assigned-right.zone-a-permit.json` | A permit issued under that programme, with `permit` and `licensePlate` credentials (fictional values) | T3 | `AssignedRight` |

`tools/validate_examples.py` patches two known upstream schema defects in memory when it validates (APDS
`Reference`, CDS Polygon `coordinates`) and prints a `NOTE` line for each on every run.
