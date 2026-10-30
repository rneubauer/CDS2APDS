/**
 * HTTP clients for the CDS Curbs API and the APDS API.
 *
 * Upstream responses are untrusted: transport failures, non-2xx statuses and
 * malformed bodies become a 502 upstream_error. Messages carry only the request
 * path, never query strings (which may contain credentials).
 */
import type { Settings } from "./config.js";
import { upstreamError } from "./errors.js";
import { isObject, type JsonObject } from "./json.js";

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

const MAX_PAGES = 1000;

class Http {
  constructor(
    private readonly fetchFn: FetchLike,
    private readonly base: string,
    private readonly headers: Record<string, string>,
    private readonly label: string,
    private readonly timeoutMs: number,
  ) {}

  async get(path: string, params?: Record<string, string>, allow404 = false): Promise<unknown> {
    const url = new URL(this.base + path);
    for (const [key, value] of Object.entries(params ?? {})) url.searchParams.set(key, value);
    let resp: Response;
    try {
      // Never follow redirects: they would carry credential query strings and X-MCC-Access-Token to another host.
      resp = await this.fetchFn(url.toString(), {
        headers: this.headers,
        redirect: "manual",
        signal: AbortSignal.timeout(this.timeoutMs),
      });
    } catch (err) {
      throw upstreamError(`${this.label} request to ${path} failed: ${(err as Error).name}`);
    }
    if (resp.status === 404 && allow404) return null;
    if (!resp.ok) throw upstreamError(`${this.label} returned HTTP ${resp.status} for ${path}`);
    try {
      return await resp.json();
    } catch {
      throw upstreamError(`${this.label} returned invalid JSON for ${path}`);
    }
  }
}

function requireObject(value: unknown, what: string): JsonObject {
  if (!isObject(value)) throw upstreamError(`malformed ${what}`);
  return value;
}

function requireList(value: unknown, what: string): JsonObject[] {
  if (!Array.isArray(value) || !value.every(isObject)) throw upstreamError(`malformed ${what}`);
  return value;
}

export class CdsClient {
  private readonly http: Http;

  constructor(fetchFn: FetchLike, settings: Settings) {
    const headers: Record<string, string> = { Accept: "application/json" };
    if (settings.cdsToken) headers.Authorization = `Bearer ${settings.cdsToken}`;
    this.http = new Http(fetchFn, settings.cdsBaseUrl, headers, "CDS", settings.httpTimeoutMs);
  }

  private async collection(name: string, optional = false): Promise<JsonObject[]> {
    const body = await this.http.get(`/curbs/${name}`, undefined, optional);
    if (body === null) return [];
    const data = requireObject(requireObject(body, `CDS ${name} response`).data, `CDS ${name} data`);
    return requireList(data[name] ?? [], `CDS ${name} list`);
  }

  private async single(name: string, id: string): Promise<JsonObject | null> {
    const body = await this.http.get(`/curbs/${name}/${encodeURIComponent(id)}`, undefined, true);
    if (body === null) return null;
    return requireObject(requireObject(body, `CDS ${name} response`).data, `CDS ${name} object`);
  }

  zones = () => this.collection("zones");
  areas = () => this.collection("areas");
  policies = () => this.collection("policies");
  objects = () => this.collection("objects", true);
  zone = (id: string) => this.single("zones", id);
  policy = (id: string) => this.single("policies", id);
}

export class ApdsClient {
  private readonly http: Http;

  constructor(fetchFn: FetchLike, settings: Settings) {
    const headers: Record<string, string> = { Accept: "application/json" };
    if (settings.apdsToken) {
      if (settings.apdsAuthScheme === "mcc") headers["X-MCC-Access-Token"] = settings.apdsToken;
      else headers.Authorization = `Bearer ${settings.apdsToken}`;
    }
    this.http = new Http(fetchFn, settings.apdsBaseUrl, headers, "APDS", settings.httpTimeoutMs);
  }

  private async paged(path: string, params: Record<string, string> = {}): Promise<JsonObject[]> {
    const items: JsonObject[] = [];
    for (let page = 1; page <= MAX_PAGES; page++) {
      const body = requireObject(await this.http.get(path, { ...params, page: String(page) }), `APDS ${path} list`);
      const batch = requireList(body.data ?? [], `APDS ${path} data`);
      const meta = requireObject(body.meta ?? {}, `APDS ${path} meta`);
      items.push(...batch);
      const total = meta.total;
      if (batch.length === 0 || !Number.isInteger(total) || items.length >= (total as number)) return items;
    }
    throw upstreamError(`APDS ${path} exceeded ${MAX_PAGES} pages`);
  }

  elements = () => this.paged("/places");

  placesNear(lat: number, lng: number, radiusM: number): Promise<JsonObject[]> {
    return this.paged("/places", {
      latitude: String(lat),
      longitude: String(lng),
      radius: String(radiusM),
      type: "place",
      expand: "occupancy,pointLocation,characteristics",
    });
  }

  rightSpecs = () => this.paged("/rights/specs");

  async rightSpec(id: string): Promise<JsonObject | null> {
    const body = await this.http.get(`/rights/specs/${encodeURIComponent(id)}`, undefined, true);
    return body === null ? null : requireObject(body, "APDS right specification");
  }

  assignedRights(specIds: string[], credential: string, credentialTypes: string): Promise<JsonObject[]> {
    return this.paged("/rights/assigned", {
      right_spec: specIds.join(","),
      credential_id: credential,
      credential_type: credentialTypes,
    });
  }
}
