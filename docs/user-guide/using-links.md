# Using links

How to answer the three curb-and-garage questions with data that is already published. You can do each one with
plain CDS and APDS API calls, or with the optional link service, which does the work for you
([API reference](../api/README.md)).

## T1: which garage entrance is on this curb?

1. Read the Curb Zone from CDS. Look in `external_references` for an entry with `name` `APDS`.
2. Fetch the APDS record at its `reference_url`. If it is a `vehicularAccess` element, it is an entrance on this curb.
3. To go the other way, read APDS elements and look for `operatorDefinedReference` with `className` `CdsCurbZone`.

With the link service: `GET /links?cds_id={curb_zone_id}`.

## T2: the curb is full, where can drivers park?

1. Take a point on the curb zone, for example the middle of its geometry.
2. Ask APDS for places nearby:
   `GET {apds-base}/places?latitude={lat}&longitude={lng}&radius={metres}&type=place&expand=occupancy`.
   **APDS radius is in metres; CDS uses centimetres.**
3. Show places linked to this curb (a supply link) first.
4. Treat a place with no occupancy data as unknown. Don't tell drivers it has space.

With the link service: `GET /zones/{curb_zone_id}/off-street?radius_m=400`.

## T3: is this permit valid at this curb?

1. Read the Curb Policies that apply to the zone. A permit policy carries an APDS `external_references` entry
   pointing at a RightSpecification (the permit programme).
2. Ask APDS who holds that permit:
   `GET {apds-base}/rights/assigned?right_spec={id}&credential_id={permit-or-plate}&credential_type=permit,licensePlate`.
3. The permit is valid if a matching right is returned, it has started and not expired, and the programme is not
   suspended. The full rule is in [profile §2.5](../02-link-profile.md#25-t3-shared-permits).

With the link service: `POST /permits/verify` with the credential in the request body, never in the URL.

**Privacy:** plates and permit numbers are personal data. Send them only to answer a check, don't log them, and
don't show them in full. The link service masks them (for example `ZA-***217`).

## When links look wrong

The link service's `GET /issues` lists references that point to records that don't exist, references to a curb
zone's previous id, and references that can't form a link, so publishers can fix their data. Each link from
`GET /links` also has a `status`: `confirmed` (declared on both sides), `cds_only` or `apds_only`.
