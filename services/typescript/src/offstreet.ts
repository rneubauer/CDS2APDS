/** T2: nearby off-street supply for a curb zone (docs/03 §3.4, profile §2.4). */
import { haversineM, pointOf, roundHalfUp, type LatLng } from "./geo.js";
import { asArray, cmp, isInteger, isNumber, isObject, isString, type JsonObject } from "./json.js";
import { parseInstant } from "./permits.js";
import type { Link } from "./registry.js";

export interface AccessPoint {
  id: string;
  name: string | null;
  access_type: unknown;
  curb_zone_id: string | null;
}

export interface PlaceSummary {
  id: string;
  version: unknown;
  name: string | null;
  linked: boolean;
  distance_m: number | null;
  spaces_total: number | null;
  spaces_available: number | null;
  occupancy_time: string | null;
  open_to_public: boolean | null;
  access_points: AccessPoint[];
  apds_url: string;
}

export function multilingual(value: unknown): string | null {
  const entries = asArray(value).filter((v): v is JsonObject => isObject(v) && isString(v.string));
  const en = entries.find((e) => e.language === "en");
  return ((en ?? entries[0])?.string as string | undefined) ?? null;
}

/** Latest demandType record by recordDateTime, read like any other instant; unreadable times are skipped. */
function latestDemand(element: JsonObject): JsonObject | null {
  const ref = element.hierarchyElementReference;
  let latest: { at: number; record: JsonObject } | null = null;
  for (const table of asArray(isObject(ref) ? ref.demandTable : undefined)) {
    for (const record of asArray(isObject(table) ? table.demandType : undefined)) {
      if (!isObject(record) || !isString(record.recordDateTime)) continue;
      const at = parseInstant(record.recordDateTime);
      if (at === null) continue;
      if (!latest || at > latest.at) latest = { at, record };
    }
  }
  return latest?.record ?? null;
}

export function spacesTotal(element: JsonObject): number | null {
  const ref = element.hierarchyElementReference;
  for (const supply of asArray(isObject(ref) ? ref.supply : undefined)) {
    if (isObject(supply) && supply.supplyViewType === "spaceView" && isInteger(supply.supplyQuantity)) return supply.supplyQuantity;
  }
  const characteristics = element.characteristics;
  const total = isObject(characteristics) ? characteristics.spacesTotal : undefined;
  return isInteger(total) ? total : null;
}

/** [spaces_total, spaces_available, occupancy_time] following profile §2.4. */
export function availability(element: JsonObject): [number | null, number | null, string | null] {
  const total = spacesTotal(element);
  const demand = latestDemand(element);
  if (!demand) return [total, null, null];
  let available: number | null = null;
  if (total !== null && isInteger(demand.count)) available = Math.max(total - demand.count, 0);
  else if (total !== null && isNumber(demand.percentage)) available = roundHalfUp(total * (1 - demand.percentage / 100));
  return [total, available, demand.recordDateTime as string];
}

export function linkedPlaceIds(zone: JsonObject, links: readonly Link[], elements: ReadonlyMap<string, JsonObject>): Set<string> {
  const zoneId = zone.curb_zone_id;
  const areaIds = new Set(asArray(zone.curb_area_ids).filter(isString));
  const found = new Set<string>();
  for (const link of links) {
    const zoneMatch = link.cds.type === "CurbZone" && link.cds.id === zoneId;
    if (link.kind === "supply" && (zoneMatch || (link.cds.type === "CurbArea" && areaIds.has(link.cds.id)))) {
      found.add(link.apds.id);
    } else if (link.kind === "access" && zoneMatch) {
      const parent = elements.get(link.apds.id)?.parentId;
      if (isObject(parent) && isString(parent.id)) found.add(parent.id);
    }
  }
  return new Set([...found].filter((id) => elements.has(id) && elements.get(id)?.type !== "vehicularAccess"));
}

export function accessPoints(placeId: string, elements: ReadonlyMap<string, JsonObject>, links: readonly Link[]): AccessPoint[] {
  const zoneFor = new Map(links.filter((l) => l.kind === "access" && l.cds.type === "CurbZone").map((l) => [l.apds.id, l.cds.id]));
  const points: AccessPoint[] = [];
  for (const element of elements.values()) {
    const parent = element.parentId;
    if (element.type === "vehicularAccess" && isObject(parent) && parent.id === placeId) {
      const id = element.id as string;
      points.push({ id, name: multilingual(element.name), access_type: element.accessType ?? null, curb_zone_id: zoneFor.get(id) ?? null });
    }
  }
  return points.sort((a, b) => cmp(a.id, b.id));
}

export function summarizePlace(
  element: JsonObject, origin: LatLng, linked: boolean,
  elements: ReadonlyMap<string, JsonObject>, links: readonly Link[], apdsBaseUrl: string,
): PlaceSummary {
  const point = pointOf(element.indicativePointLocation);
  const [total, available, occupancyTime] = availability(element);
  const characteristics = element.characteristics;
  const open = isObject(characteristics) ? characteristics.openToPublic : undefined;
  const id = element.id as string;
  return {
    id,
    version: element.version ?? null,
    name: multilingual(element.name),
    linked,
    distance_m: point ? roundHalfUp(haversineM(origin[0], origin[1], point[0], point[1])) : null,
    spaces_total: total,
    spaces_available: available,
    occupancy_time: occupancyTime,
    open_to_public: typeof open === "boolean" ? open : null,
    access_points: accessPoints(id, elements, links),
    apds_url: `${apdsBaseUrl}/places/${id}`,
  };
}

export function buildSummary(
  zone: JsonObject, origin: LatLng, radiusM: number, nearby: readonly JsonObject[],
  elements: ReadonlyMap<string, JsonObject>, links: readonly Link[], apdsBaseUrl: string,
) {
  const linkedIds = linkedPlaceIds(zone, links, elements);
  const candidates = new Map<string, JsonObject>([...linkedIds].map((id) => [id, elements.get(id) as JsonObject]));
  for (const element of nearby) if (isString(element.id)) candidates.set(element.id, element);
  const places = [...candidates].map(([id, el]) => summarizePlace(el, origin, linkedIds.has(id), elements, links, apdsBaseUrl));
  places.sort(
    (a, b) =>
      Number(!a.linked) - Number(!b.linked) ||
      Number(a.distance_m === null) - Number(b.distance_m === null) ||
      (a.distance_m ?? 0) - (b.distance_m ?? 0) ||
      cmp(a.id, b.id),
  );
  return { curb_zone_id: zone.curb_zone_id, origin: { lat: origin[0], lng: origin[1] }, radius_m: radiusM, places };
}
