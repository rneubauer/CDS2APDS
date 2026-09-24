/** Link service orchestration: combines the registry with live upstream reads (docs/03 §3.4). */
import type { Settings } from "./config.js";
import { invalidRequest, notFound, upstreamError } from "./errors.js";
import { centroid, type LatLng } from "./geo.js";
import { asArray, isObject, isString, type JsonObject } from "./json.js";
import { buildSummary } from "./offstreet.js";
import * as permits from "./permits.js";
import { apdsSnapshot, Registry } from "./registry.js";
import { ApdsClient, CdsClient, type FetchLike } from "./upstream.js";

export class LinkService {
  readonly registry: Registry;
  private readonly cds: CdsClient;
  private readonly apds: ApdsClient;
  private syncing: Promise<void> | null = null;

  constructor(readonly settings: Settings, fetchFn: FetchLike, readonly clock: () => number, maxRegistryEntries?: number) {
    this.registry = new Registry(maxRegistryEntries);
    this.cds = new CdsClient(fetchFn, settings);
    this.apds = new ApdsClient(fetchFn, settings);
  }

  /** Re-harvest both sides. Concurrent callers share one in-flight sync. */
  sync(): Promise<void> {
    this.syncing ??= this.harvest().finally(() => {
      this.syncing = null;
    });
    return this.syncing;
  }

  private async harvest(): Promise<void> {
    const [zones, areas, objects, policies, elements, specs] = await Promise.all([
      this.cds.zones(), this.cds.areas(), this.cds.objects(), this.cds.policies(),
      this.apds.elements(), this.apds.rightSpecs(),
    ]);
    this.registry.replace({ zones, areas, objects, policies }, apdsSnapshot(elements, specs), permits.formatInstant(this.clock()));
  }

  async ensureSynced(): Promise<void> {
    if (!this.registry.synced) await this.sync();
  }

  private async zone(zoneId: string): Promise<JsonObject> {
    const zone = await this.cds.zone(zoneId);
    if (!zone) throw notFound(`curb zone ${zoneId} not found`);
    return zone;
  }

  async offStreet(zoneId: string, radiusM: number) {
    await this.ensureSynced();
    const zone = await this.zone(zoneId);
    let origin: LatLng;
    try {
      origin = centroid(zone.geometry);
    } catch (err) {
      throw upstreamError(`curb zone ${zoneId} has unusable geometry: ${(err as Error).message}`);
    }
    const nearby = await this.apds.placesNear(origin[0], origin[1], radiusM);
    const reg = this.registry;
    return buildSummary(zone, origin, radiusM, nearby, reg.apds.elements, reg.links, this.settings.apdsBaseUrl);
  }

  async verifyPermit(zoneId: string, credential: string, credentialType: string | undefined, at: number) {
    const zone = await this.zone(zoneId);
    const policyIds = asArray(zone.curb_policy_ids).filter(isString);
    const policies = (await Promise.all(policyIds.map((id) => this.cds.policy(id)))).filter((p): p is JsonObject => p !== null);
    const progs = permits.programmes(policies);
    const base = {
      curb_zone_id: zoneId,
      at: permits.formatInstant(at),
      programmes: progs,
      credential_masked: permits.maskCredential(credential),
    };
    if (progs.length === 0) return { ...base, result: "no_programme", assigned_right: null };

    const specIds = [...new Set(progs.map((p) => p.right_specification_id))].sort();
    const rights = await this.apds.assignedRights(specIds, credential, credentialType ?? "permit,licensePlate");
    const specOf = (r: JsonObject) => (isObject(r.rightSpecification) ? r.rightSpecification.id : undefined);
    const candidates = rights.filter((r) => {
      const specId = specOf(r);
      return isString(specId) && specIds.includes(specId) && permits.holdsCredential(r, credential);
    });
    const needed = [...new Set(candidates.map((r) => specOf(r) as string))].sort();
    const specs = new Map(await Promise.all(needed.map(async (id) => [id, await this.apds.rightSpec(id)] as const)));
    const outcomes = candidates.map((r) => [r, permits.evaluate(r, specs.get(specOf(r) as string), at)] as const);
    const [result, right] = permits.decide(outcomes);
    return { ...base, result, assigned_right: permits.rightSummary(right) };
  }

  async applyWebhook(eventType: string, body: JsonObject): Promise<boolean> {
    await this.ensureSynced();
    const deleted = eventType.endsWith("Deleted");
    const id = body.id as string;
    if (/^Place(Created|Updated|Deleted)$/.test(eventType)) {
      if (deleted) this.registry.removeElement(id);
      else if (!this.registry.upsertElement(body)) throw invalidRequest("registry is full; new APDS elements are refused");
      return true;
    }
    if (/^RightSpecification(Created|Updated|Deleted)$/.test(eventType)) {
      if (deleted) this.registry.removeRightSpec(id);
      else if (!this.registry.upsertRightSpec(body)) throw invalidRequest("registry is full; new right specifications are refused");
      return true;
    }
    return false;
  }
}
