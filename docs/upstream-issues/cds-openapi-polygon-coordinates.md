# Draft issue: openmobilityfoundation/cds-openapi

Status: **draft, not filed.** Filing needs Rick's OK.

---

**Title:** `geoJSON_polygon.yaml`: `coordinates` has LineString shape, not RFC 7946 Polygon shape

## Summary

`Shared Data Models/geoJSON_polygon.yaml` describes a GeoJSON Polygon "as defined in RFC 7946 3.1.6",
but its `coordinates` property references `coordinates.yaml`, which is an array of positions. That is
the shape of a LineString. An RFC 7946 Polygon's `coordinates` is an array of linear rings, each an
array of positions. As a result, valid CDS Curb Zone and Curb Area geometries fail schema validation,
and payloads that pass validation are not valid GeoJSON.

## Where

At `6f8f4a78b32586f84a67d6ac3a10bf2cfec992a3`:

- `Shared Data Models/geoJSON_polygon.yaml`: `coordinates: { $ref: ./coordinates.yaml }`
- `Shared Data Models/coordinates.yaml`: `type: array`, `items: { type: array, minItems: 2, maxItems: 2, items: { type: number } }`

## Example

This RFC 7946 Polygon is rejected:

```json
{ "type": "Polygon", "coordinates": [[[-73.9821, 40.7679], [-73.9737, 40.7646], [-73.9493, 40.7969], [-73.9821, 40.7679]]] }
```

## Suggested fix

```yaml
coordinates:
  type: array
  items:
    $ref: ./coordinates.yaml
```

Optionally also require each ring to be closed with at least four positions (`minItems: 4`).

---

**Second, smaller point (same files), could be a separate issue or folded in:**

**Title:** `coordinates.yaml` description says "latitude and longitude"; RFC 7946 order is longitude, latitude

The description reads "These represent the latitude and longitude." RFC 7946 §3.1.1 and the CDS prose
spec use **longitude, latitude**, and the file's own example is in lon/lat order (`[-73.98, 40.77]`).
Suggested fix: "Each position is [longitude, latitude] (RFC 7946 §3.1.1)."
