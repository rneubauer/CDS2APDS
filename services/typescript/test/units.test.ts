/** Unit tests for behaviour the shared conformance fixtures do not exercise. */
import { describe, expect, it } from "vitest";
import { buildApp } from "../src/app.js";
import { settingsFromEnv } from "../src/config.js";
import { centroid, pointOf, roundHalfUp } from "../src/geo.js";
import { availability, multilingual } from "../src/offstreet.js";
import { decide, evaluate, maskCredential, parseInstant, programmeActive } from "../src/permits.js";
import { apdsSnapshot, buildLinks, emptyCds, parseApdsReference, Registry } from "../src/registry.js";
import type { FetchLike } from "../src/upstream.js";
import { FIXTURES, FakeUpstream } from "./fake-upstream.js";

const AT = Date.parse("2026-06-01T00:00:00Z");
const APDS = "https://apds.example.org/v4";
const ext = (url: string, ids?: string[], name = "APDS") => ({ name, reference_url: url, ...(ids ? { ids } : {}) });

describe("config", () => {
  it("validates environment variables", () => {
    expect(() => settingsFromEnv({ APDS_BASE_URL: APDS })).toThrow("CDS_BASE_URL is required");
    expect(() => settingsFromEnv({ CDS_BASE_URL: "cds.example.org", APDS_BASE_URL: APDS })).toThrow("absolute");
    expect(() => settingsFromEnv({ CDS_BASE_URL: "ftp://c", APDS_BASE_URL: APDS })).toThrow("absolute");
    expect(() => settingsFromEnv({ CDS_BASE_URL: "https://c", APDS_BASE_URL: APDS, DEFAULT_RADIUS_M: "9000" })).toThrow("between");
    expect(() => settingsFromEnv({ CDS_BASE_URL: "https://c", APDS_BASE_URL: APDS, PORT: "x" })).toThrow("integer");
    expect(() => settingsFromEnv({ CDS_BASE_URL: "https://c", APDS_BASE_URL: APDS, APDS_AUTH_SCHEME: "basic" })).toThrow("one of");
    const s = settingsFromEnv({ CDS_BASE_URL: "https://c/", APDS_BASE_URL: `${APDS}/`, APDS_AUTH_SCHEME: "MCC" });
    expect([s.cdsBaseUrl, s.apdsBaseUrl, s.apdsAuthScheme, s.port]).toEqual(["https://c", APDS, "mcc", 8080]);
  });
});

describe("references and registry", () => {
  it("parses APDS reference variants", () => {
    expect(parseApdsReference(ext(`${APDS}/places/p1`))).toEqual(["places", "p1"]);
    expect(parseApdsReference(ext(`${APDS}/places/p1`, ["p2"]))).toEqual(["places", "p2"]);
    expect(parseApdsReference(ext(`${APDS}/rights/specs/r1`))).toEqual(["rights/specs", "r1"]);
    expect(parseApdsReference(ext(`${APDS}/places/p1`, undefined, "apds"))).toEqual(["places", "p1"]);
    expect(parseApdsReference(ext(`${APDS}/places`))).toEqual(["", ""]);
    expect(parseApdsReference(ext(`${APDS}/sessions/s1`))).toEqual(["", ""]);
    expect(parseApdsReference(ext("not a url"))).toEqual(["", ""]);
    expect(parseApdsReference(ext(`${APDS}/places/p1`, undefined, "WZDx"))).toBeNull();
    expect(parseApdsReference("not an object")).toBeNull();
  });

  it("re-points stale zone references", () => {
    const cds = { ...emptyCds(), zones: [{ curb_zone_id: "z-new", prev_curb_zone_ids: ["z-old"] }] };
    const apds = apdsSnapshot(
      [{ id: "va1", type: "vehicularAccess", operatorDefinedReference: { id: "z-old", version: 1, className: "CdsCurbZone" } }],
      [],
    );
    const { links, issues } = buildLinks(cds, apds);
    expect(links.map((l) => [l.kind, l.status, l.cds.id])).toEqual([["access", "apds_only", "z-new"]]);
    expect(issues.map((i) => i.code)).toEqual(["stale_cds_reference"]);
  });

  it("reports missing and invalid references", () => {
    const cds = {
      ...emptyCds(),
      zones: [{ curb_zone_id: "z1", external_references: [ext(`${APDS}/rights/specs/r1`), ext(`${APDS}/bogus`)] }],
      policies: [{ curb_policy_id: "p1", external_references: [ext(`${APDS}/places/pl1`), ext(`${APDS}/rights/specs/missing`)] }],
    };
    const apds = apdsSnapshot(
      [
        { id: "pl1", type: "place", operatorDefinedReference: { id: "gone", version: 1, className: "CdsCurbArea" } },
        { id: "pl2", type: "place", operatorDefinedReference: { id: "x", version: 1, className: "SomethingElse" } },
      ],
      [],
    );
    const { links, issues } = buildLinks(cds, apds);
    expect(links.map((l) => [l.kind, l.status, l.apds.id])).toEqual([["permit", "cds_only", "missing"]]);
    expect(issues.map((i) => i.code).sort()).toEqual([
      "apds_target_missing", "cds_target_missing", "invalid_reference", "invalid_reference", "invalid_reference",
    ]);
  });
});

describe("geometry and availability", () => {
  it("computes centroids and rejects bad geometry", () => {
    expect(centroid({ type: "LineString", coordinates: [[0, 0], [2, 2]] })).toEqual([1, 1]);
    expect(centroid({ type: "Point", coordinates: [3, 4] })).toEqual([4, 3]);
    for (const bad of [null, { type: "Polygon", coordinates: [] }, { type: "Circle" }, { type: "LineString", coordinates: [["a", 1]] }]) {
      expect(() => centroid(bad)).toThrow();
    }
    expect(pointOf([{ type: "Polygon" }])).toBeNull();
    expect(pointOf([])).toBeNull();
    expect([roundHalfUp(2.5), roundHalfUp(-0.5)]).toEqual([3, 0]);
  });

  it("derives availability", () => {
    const table = (rec: object[]) => ({
      hierarchyElementReference: { supply: [{ supplyViewType: "spaceView", supplyQuantity: 10 }], demandTable: [{ demandType: rec }] },
    });
    expect(availability(table([{ recordDateTime: "2026-01-01T00:00:00Z", count: 12 }]))).toEqual([10, 0, "2026-01-01T00:00:00Z"]);
    const latest = table([
      { recordDateTime: "2026-01-01T00:00:00Z", count: 1 },
      { recordDateTime: "2026-01-02T00:00:00Z", count: 4 },
    ]);
    expect(availability(latest)).toEqual([10, 6, "2026-01-02T00:00:00Z"]);
    expect(availability(table([{ recordDateTime: "2026-01-01T00:00:00Z", percentage: 25 }]))[1]).toBe(8);
    expect(availability({ characteristics: { spacesTotal: 5 } })).toEqual([5, null, null]);
    expect(multilingual([{ language: "fr", string: "Parc" }])).toBe("Parc");
    expect(multilingual(null)).toBeNull();
  });
});

describe("permit evaluation", () => {
  const spec = { validity: { validityStatus: "definedByValidityTimeSpec", validityTimeSpecification: { overallStartTime: "2026-01-01T00:00:00Z" } } };

  it("checks programme activity", () => {
    expect(programmeActive(spec, AT)).toBe(true);
    expect(programmeActive(null, AT)).toBe(false);
    expect(programmeActive({ validity: { validityStatus: "suspended", validityTimeSpecification: { overallStartTime: "2026-01-01T00:00:00Z" } } }, AT)).toBe(false);
    expect(programmeActive({ validity: { validityTimeSpecification: { overallStartTime: "2026-01-01T00:00:00Z", overallEndTime: "2026-06-01T00:00:00Z" } } }, AT)).toBe(false);
    expect(evaluate({ id: "a" }, null, AT)).toBe("programme_inactive");
  });

  it("prefers valid rights, then the latest expiry", () => {
    const r1 = { id: "r1", expiry: "2026-07-01T00:00:00Z" };
    const r2 = { id: "r2", expiry: "2026-09-01T00:00:00Z" };
    const r3 = { id: "r3" };
    expect(decide([])).toEqual(["not_found", null]);
    expect(decide([[r1, "valid"], [r2, "valid"]])).toEqual(["valid", r2]);
    expect(decide([[r1, "valid"], [r3, "valid"]])).toEqual(["valid", r3]);
    expect(decide([[r1, "expired"], [r2, "programme_inactive"]])).toEqual(["programme_inactive", r2]);
  });

  it("masks credentials and parses instants", () => {
    expect(maskCredential("ABC")).toBe("***");
    expect(maskCredential("ABCDEFG")).toBe("ABC***EFG");
    expect(parseInstant("2026-01-01T00:00:00")).toBe(Date.parse("2026-01-01T00:00:00Z"));
    expect(parseInstant("2026-01-01")).toBe(Date.parse("2026-01-01T00:00:00Z"));
    expect(parseInstant("soon")).toBeNull();
  });
});

describe("HTTP edge cases", () => {
  const app = (fetchFn?: FetchLike, env: Record<string, string> = {}) =>
    buildApp(settingsFromEnv({ ...FIXTURES.config, ...env }), { fetch: fetchFn ?? new FakeUpstream().fetch });

  it("turns upstream failures into 502", async () => {
    const failing = app(async (url) => {
      if (url.includes("credential")) throw new TypeError("boom");
      return new Response("{}", { status: 500 });
    });
    const resp = await failing.inject({ method: "POST", url: "/sync" });
    expect([resp.statusCode, resp.json().error.code]).toEqual([502, "upstream_error"]);
    const notJson = app(async () => new Response("not json", { status: 200 }));
    expect((await notJson.inject({ method: "GET", url: "/links" })).json().error.code).toBe("upstream_error");
    const malformed = app(async () => new Response(JSON.stringify({ data: { zones: "nope" } }), { status: 200 }));
    expect((await malformed.inject({ method: "POST", url: "/sync" })).statusCode).toBe(502);
    const offline = app(async () => { throw new TypeError("offline"); });
    expect((await offline.inject({ method: "POST", url: "/sync" })).statusCode).toBe(502);
  });

  it("sends upstream auth headers and never echoes credentials", async () => {
    const upstream = new FakeUpstream();
    const svc = app(upstream.fetch, { CDS_TOKEN: "c-tok", APDS_TOKEN: "a-tok", APDS_AUTH_SCHEME: "mcc" });
    const resp = await svc.inject({
      method: "POST", url: "/permits/verify",
      payload: { curb_zone_id: "3f2a9c1e-5b7d-4e8a-9c01-00000000b003", credential: "ZA-004217" },
    });
    expect(resp.statusCode).toBe(200);
    expect(resp.body).not.toContain("ZA-004217");
    const cdsReq = upstream.requests.find((r) => r.url.host === "cds.example.org");
    const apdsReq = upstream.requests.find((r) => r.url.host === "apds.example.org");
    expect(cdsReq?.headers.get("authorization")).toBe("Bearer c-tok");
    expect(apdsReq?.headers.get("x-mcc-access-token")).toBe("a-tok");
    expect(apdsReq?.headers.get("authorization")).toBeNull();

    const bearer = new FakeUpstream();
    await app(bearer.fetch, { APDS_TOKEN: "a-tok" }).inject({ method: "POST", url: "/sync" });
    expect(bearer.requests.find((r) => r.url.host === "apds.example.org")?.headers.get("authorization")).toBe("Bearer a-tok");
  });

  it("validates request bodies and routes", async () => {
    const svc = app();
    const post = (payload: unknown, headers: Record<string, string> = {}) =>
      svc.inject({ method: "POST", url: "/permits/verify", payload: payload as string, headers });
    expect((await post("{bad", { "content-type": "application/json" })).statusCode).toBe(400);
    expect((await post([1])).statusCode).toBe(400);
    expect((await post({ curb_zone_id: "z", credential: "x", at: 5 })).statusCode).toBe(400);
    const hdrs = { "X-APDS-Event-Type": "PlaceUpdated", "X-Link-Webhook-Token": "conformance-token" };
    expect((await svc.inject({ method: "POST", url: "/webhooks/apds", payload: { version: 1 }, headers: hdrs })).statusCode).toBe(400);
    expect((await svc.inject({ method: "GET", url: "/links?kind=a&kind=b" })).statusCode).toBe(400);
    const missing = await svc.inject({ method: "GET", url: "/nope" });
    expect([missing.statusCode, missing.json().error.code]).toEqual([404, "not_found"]);
  });

  it("applies RightSpecification webhook events", async () => {
    const svc = app();
    const hdrs = { "X-Link-Webhook-Token": "conformance-token" };
    const specId = "7d41e6b2-8c3f-4a9d-b210-00000000f101";
    const del = await svc.inject({ method: "POST", url: "/webhooks/apds", payload: { id: specId }, headers: { ...hdrs, "X-APDS-Event-Type": "RightSpecificationDeleted" } });
    expect(del.json().data.applied).toBe(true);
    expect((await svc.inject({ method: "GET", url: "/issues" })).json().data[0].code).toBe("apds_target_missing");
    await svc.inject({ method: "POST", url: "/webhooks/apds", payload: { id: specId, version: 2 }, headers: { ...hdrs, "X-APDS-Event-Type": "RightSpecificationUpdated" } });
    expect((await svc.inject({ method: "GET", url: "/issues" })).json().data).toEqual([]);
  });

  it("accepts webhooks without a configured token and rejects zones with bad geometry", async () => {
    const fake = new FakeUpstream();
    const svc = app(async (url, init) =>
      url.endsWith("/curbs/zones/zbad")
        ? new Response(JSON.stringify({ data: { curb_zone_id: "zbad", geometry: { type: "Circle" } } }), { status: 200 })
        : fake.fetch(url, init),
    { LINK_WEBHOOK_TOKEN: "" });
    const r = await svc.inject({ method: "POST", url: "/webhooks/apds", payload: { id: "s" }, headers: { "X-APDS-Event-Type": "RateUpdated" } });
    expect([r.statusCode, r.json().data.applied]).toEqual([200, false]);
    expect((await svc.inject({ method: "GET", url: "/zones/zbad/off-street" })).statusCode).toBe(502);
  });
});

describe("review regressions", () => {
  const spec = { validity: { validityStatus: "definedByValidityTimeSpec", validityTimeSpecification: { overallStartTime: "2026-01-01T00:00:00Z" } } };
  const app = (fetchFn?: FetchLike) => buildApp(settingsFromEnv(FIXTURES.config), { fetch: fetchFn ?? new FakeUpstream().fetch });

  it("fails closed on unparseable timestamps", () => {
    expect(evaluate({ id: "a", expiry: "2028-01-01T00:00:00+0000" }, spec, AT)).toBe("expired");
    expect(evaluate({ id: "a", issuanceTime: "garbage" }, spec, AT)).toBe("not_yet_valid");
    const badEnd = { validity: { validityTimeSpecification: { overallStartTime: "2026-01-01T00:00:00Z", overallEndTime: "soon" } } };
    expect(programmeActive(badEnd, AT)).toBe(false);
    for (const text of ["2026-06-01 12:00:00+00:00", "2026-06-01T12:00:00+0000", "20260601"]) expect(parseInstant(text)).toBeNull();
  });

  it("requires absolute http(s) reference URLs", () => {
    expect(parseApdsReference(ext("/places/p1"))).toEqual(["", ""]);
    expect(parseApdsReference(ext("ftp://apds.example.org/places/p1"))).toEqual(["", ""]);
  });

  it("refuses new ids beyond the registry cap", async () => {
    const reg = new Registry(1);
    expect([reg.upsertElement({ id: "a" }), reg.upsertElement({ id: "a", version: 2 }), reg.upsertElement({ id: "b" })]).toEqual([true, true, false]);
    expect([reg.upsertRightSpec({ id: "s" }), reg.upsertRightSpec({ id: "t" })]).toEqual([true, false]);

    const hdrs = { "X-APDS-Event-Type": "PlaceCreated", "X-Link-Webhook-Token": "conformance-token" };
    const small = buildApp(settingsFromEnv(FIXTURES.config), { fetch: new FakeUpstream().fetch, maxRegistryEntries: 4 });
    const resp = await small.inject({ method: "POST", url: "/webhooks/apds", payload: { id: "new-place", type: "place" }, headers: hdrs });
    expect(resp.statusCode).toBe(400);
    expect(resp.json().error.message).toContain("full");
  });

  it("keeps caller ids as one upstream path segment", async () => {
    const upstream = new FakeUpstream();
    const resp = await app(upstream.fetch).inject({
      method: "POST", url: "/permits/verify", payload: { curb_zone_id: "../policies/x?y=1", credential: "ZA-004217" },
    });
    expect(resp.statusCode).toBe(404);
    const cdsPaths = upstream.requests.filter((r) => r.url.host === "cds.example.org").map((r) => r.url.pathname);
    expect(cdsPaths).toEqual(["/curbs/zones/..%2Fpolicies%2Fx%3Fy%3D1"]);
  });

  it("rejects oversized bodies", async () => {
    const resp = await app().inject({
      method: "POST", url: "/permits/verify", payload: { curb_zone_id: "z", credential: "x", pad: "a".repeat(1_100_000) },
    });
    expect(resp.statusCode).toBe(400);
  });
});
