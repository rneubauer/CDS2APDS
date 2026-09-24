/** In-memory CDS + APDS servers implementing conformance/fixtures.json "fake_upstream" rules. */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import type { FetchLike } from "../src/upstream.js";

type Obj = Record<string, any>;

export const REPO = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
export const loadJson = (path: string): any => JSON.parse(readFileSync(path, "utf-8"));
export const FIXTURES = loadJson(join(REPO, "conformance", "fixtures.json"));
export const CASES: any[] = loadJson(join(REPO, "conformance", "cases.json"));

const PLACES_PARAMS = new Set(["page", "latitude", "longitude", "radius", "type", "expand"]);
const SPECS_PARAMS = new Set(["page"]);
const ASSIGNED_PARAMS = new Set(["page", "right_spec", "credential_id", "credential_type"]);

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

function haversine(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const r = (d: number) => (d * Math.PI) / 180;
  const a = Math.sin(r(lat2 - lat1) / 2) ** 2 + Math.cos(r(lat1)) * Math.cos(r(lat2)) * Math.sin(r(lng2 - lng1) / 2) ** 2;
  return 2 * 6_371_008.8 * Math.asin(Math.sqrt(a));
}

function paged(items: Obj[], pageSize: number, pageRaw: string | null) {
  const offset = (Number(pageRaw ?? "1") - 1) * pageSize;
  return json(200, {
    data: items.slice(offset, offset + pageSize),
    meta: { referenceInstant: 0, offset, pageSize, total: items.length },
  });
}

const unknownParams = (params: URLSearchParams, allowed: Set<string>) => [...params.keys()].some((k) => !allowed.has(k));

export class FakeUpstream {
  readonly requests: Array<{ url: URL; headers: Headers }> = [];
  private readonly cdsHost: string;
  private readonly apdsHost: string;
  private readonly apdsPrefix: string;
  readonly zones: Obj[];
  readonly areas: Obj[];
  readonly policies: Obj[];
  readonly elements: Obj[];
  readonly specs: Obj[];
  readonly assigned: Obj[];

  constructor(fixtures: any = FIXTURES) {
    const load = (files: string[]) => files.map((f) => loadJson(join(REPO, "examples", f)));
    this.cdsHost = new URL(fixtures.config.CDS_BASE_URL).host;
    const apds = new URL(fixtures.config.APDS_BASE_URL);
    this.apdsHost = apds.host;
    this.apdsPrefix = apds.pathname.replace(/\/$/, "");
    this.zones = load(fixtures.cds.zones);
    this.areas = load(fixtures.cds.areas);
    this.policies = load(fixtures.cds.policies);
    this.elements = load(fixtures.apds.elements);
    this.specs = load(fixtures.apds.right_specs);
    this.assigned = load(fixtures.apds.assigned_rights);
  }

  readonly fetch: FetchLike = async (input, init) => {
    const url = new URL(input);
    this.requests.push({ url, headers: new Headers(init?.headers) });
    if ((init?.method ?? "GET") !== "GET") return json(405, {});
    if (url.host === this.cdsHost) return this.cds(url.pathname);
    if (url.host === this.apdsHost && url.pathname.startsWith(this.apdsPrefix)) {
      return this.apds(url.pathname.slice(this.apdsPrefix.length), url.searchParams);
    }
    return json(404, {});
  };

  private cds(path: string): Response {
    const parts = path.split("/").filter(Boolean);
    const collections: Record<string, [Obj[], string]> = {
      zones: [this.zones, "curb_zone_id"],
      areas: [this.areas, "curb_area_id"],
      policies: [this.policies, "curb_policy_id"],
    };
    const entry = parts[0] === "curbs" && parts[1] ? collections[parts[1]] : undefined;
    if (!entry) return json(404, {});
    const [items, key] = entry;
    if (parts.length === 2) return json(200, { version: "1.1", data: { [parts[1] as string]: items } });
    const match = items.find((i) => i[key] === parts[2]);
    return match ? json(200, { version: "1.1", data: match }) : json(404, {});
  }

  private apds(path: string, params: URLSearchParams): Response {
    const parts = path.split("/").filter(Boolean);
    const key = parts.join("/");
    if (key === "places") return this.places(params);
    if (parts.length === 2 && parts[0] === "places") return this.byId(this.elements, parts[1] as string);
    if (key === "rights/specs") return unknownParams(params, SPECS_PARAMS) ? json(400, {}) : paged(this.specs, 2, params.get("page"));
    if (parts.length === 3 && key.startsWith("rights/specs/")) return this.byId(this.specs, parts[2] as string);
    if (key === "rights/assigned") return this.assignedRights(params);
    return json(404, {});
  }

  private byId(items: Obj[], id: string): Response {
    const match = items.find((i) => i.id === id);
    return match ? json(200, match) : json(404, { status: "error", code: 404 });
  }

  private places(params: URLSearchParams): Response {
    if (unknownParams(params, PLACES_PARAMS)) return json(400, {});
    let items = this.elements;
    const type = params.get("type");
    if (type) items = items.filter((e) => type.split(",").includes(e.type));
    if (params.has("radius")) {
      const lat = Number(params.get("latitude"));
      const lng = Number(params.get("longitude"));
      const radius = Number(params.get("radius"));
      items = items.filter((e) => {
        const coords = e.indicativePointLocation?.[0]?.coordinates;
        return coords ? haversine(lat, lng, coords[1], coords[0]) <= radius : false;
      });
    }
    return paged(items, 2, params.get("page"));
  }

  private assignedRights(params: URLSearchParams): Response {
    if (unknownParams(params, ASSIGNED_PARAMS)) return json(400, {});
    const specs = params.has("right_spec") ? (params.get("right_spec") as string).split(",") : null;
    const types = params.has("credential_type") ? (params.get("credential_type") as string).split(",") : null;
    const wanted = params.get("credential_id");
    const matches = (r: Obj) =>
      (specs === null || specs.includes(r.rightSpecification.id)) &&
      (wanted === null ||
        r.rightHolder.credentials.some((c: Obj) => c.identifier.id === wanted && (types === null || types.includes(c.type))));
    return paged(this.assigned.filter(matches), 100, params.get("page"));
  }
}
