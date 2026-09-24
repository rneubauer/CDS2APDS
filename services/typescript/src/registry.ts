/** Link registry: harvest declarations from both sides and merge them (docs/03 §3.3). */
import { asArray, cmp, isObject, isString, type JsonObject } from "./json.js";

export const LINK_KINDS = ["access", "permit", "supply"] as const;
export type LinkKind = (typeof LINK_KINDS)[number];
export type LinkStatus = "confirmed" | "cds_only" | "apds_only";
export type CdsType = "CurbZone" | "CurbArea" | "CurbSpace" | "CurbObject" | "CurbPolicy";

export const CDS_ID_FIELDS: Record<CdsType, string> = {
  CurbZone: "curb_zone_id",
  CurbArea: "curb_area_id",
  CurbSpace: "curb_space_id",
  CurbObject: "curb_object_id",
  CurbPolicy: "curb_policy_id",
};
const CLASSNAME_TO_CDS: Record<string, CdsType> = {
  CdsCurbZone: "CurbZone",
  CdsCurbArea: "CurbArea",
  CdsCurbSpace: "CurbSpace",
  CdsCurbObject: "CurbObject",
};

export const PLACES = "places";
export const RIGHT_SPECS = "rights/specs";

/** Webhook upserts of new ids are refused beyond this many elements (or right specifications). */
export const MAX_REGISTRY_ENTRIES = 100_000;

export interface Ref {
  readonly type: string;
  readonly id: string;
}
export interface Link {
  readonly kind: LinkKind;
  readonly status: LinkStatus;
  readonly cds: Ref;
  readonly apds: Ref;
}
export interface Issue {
  readonly code: string;
  readonly cds: Ref | null;
  readonly apds: Ref | null;
  readonly detail: string;
}

export interface CdsSnapshot {
  readonly zones: readonly JsonObject[];
  readonly areas: readonly JsonObject[];
  readonly objects: readonly JsonObject[];
  readonly policies: readonly JsonObject[];
}
export interface ApdsSnapshot {
  readonly elements: ReadonlyMap<string, JsonObject>;
  readonly rightSpecs: ReadonlyMap<string, JsonObject>;
}

export const emptyCds = (): CdsSnapshot => ({ zones: [], areas: [], objects: [], policies: [] });

function byId(items: readonly JsonObject[]): Map<string, JsonObject> {
  return new Map(items.filter((i) => isString(i.id)).map((i) => [i.id as string, i]));
}

export function apdsSnapshot(elements: readonly JsonObject[], rightSpecs: readonly JsonObject[]): ApdsSnapshot {
  return { elements: byId(elements), rightSpecs: byId(rightSpecs) };
}

function cdsRecords(cds: CdsSnapshot): Array<[CdsType, JsonObject]> {
  return [
    ...cds.zones.map((z): [CdsType, JsonObject] => ["CurbZone", z]),
    ...cds.areas.map((a): [CdsType, JsonObject] => ["CurbArea", a]),
    ...cds.objects.map((o): [CdsType, JsonObject] => ["CurbObject", o]),
    ...cds.policies.map((p): [CdsType, JsonObject] => ["CurbPolicy", p]),
  ];
}

export type ParsedRef = readonly [collection: string, id: string];

/** [collection, id] for an APDS external reference; null if not APDS; ["", ""] if unusable. */
export function parseApdsReference(ref: unknown): ParsedRef | null {
  if (!isObject(ref) || String(ref.name ?? "").toLowerCase() !== "apds") return null;
  // Profile §2.2: reference_url MUST be an absolute URL; anything else is unusable.
  let path = "";
  try {
    const url = new URL(String(ref.reference_url ?? ""));
    path = url.protocol === "http:" || url.protocol === "https:" ? url.pathname : "";
  } catch {
    path = "";
  }
  const segments = path.split("/").filter(Boolean);
  const ids = ref.ids;
  const explicit = Array.isArray(ids) && isString(ids[0]) && ids[0] ? ids[0] : null;
  for (let i = 0; i < segments.length; i++) {
    if (segments[i] === "rights" && segments[i + 1] === "specs") {
      const id = explicit ?? segments[i + 2];
      return id ? [RIGHT_SPECS, id] : ["", ""];
    }
    if (segments[i] === "places") {
      const id = explicit ?? segments[i + 1];
      return id ? [PLACES, id] : ["", ""];
    }
  }
  return ["", ""];
}

export function apdsReferences(record: JsonObject): ParsedRef[] {
  return asArray(record.external_references)
    .map(parseApdsReference)
    .filter((r): r is ParsedRef => r !== null);
}

class Merger {
  private readonly entries = new Map<string, { kind: LinkKind; cds: Ref; apds: Ref; sides: Set<string> }>();
  private readonly issues = new Map<string, Issue>();

  add(kind: LinkKind, cds: Ref, apds: Ref, side: "cds" | "apds"): void {
    const key = JSON.stringify([cds.type, cds.id, apds.id]);
    const entry = this.entries.get(key) ?? { kind, cds, apds, sides: new Set<string>() };
    entry.sides.add(side);
    this.entries.set(key, entry);
  }

  issue(code: string, cds: Ref | null, apds: Ref | null, detail: string): void {
    this.issues.set(JSON.stringify([code, cds, apds, detail]), { code, cds, apds, detail });
  }

  result(): { links: Link[]; issues: Issue[] } {
    const links = [...this.entries.values()].map((e): Link => ({
      kind: e.kind,
      status: e.sides.size === 2 ? "confirmed" : e.sides.has("cds") ? "cds_only" : "apds_only",
      cds: e.cds,
      apds: e.apds,
    }));
    links.sort((a, b) => cmp(a.kind, b.kind) || cmp(a.cds.type, b.cds.type) || cmp(a.cds.id, b.cds.id) || cmp(a.apds.id, b.apds.id));
    const issues = [...this.issues.values()];
    issues.sort((a, b) => cmp(a.code, b.code) || cmp(a.cds?.id ?? "", b.cds?.id ?? "") || cmp(a.apds?.id ?? "", b.apds?.id ?? "") || cmp(a.detail, b.detail));
    return { links, issues };
  }
}

function cdsPermit(cref: Ref, apdsId: string, apds: ApdsSnapshot, merger: Merger): void {
  const aref = { type: "RightSpecification", id: apdsId };
  if (cref.type !== "CurbPolicy") {
    merger.issue("invalid_reference", cref, aref, `only a CurbPolicy may reference a RightSpecification, not ${cref.type}`);
    return;
  }
  if (!apds.rightSpecs.has(apdsId)) {
    merger.issue("apds_target_missing", cref, aref, `CurbPolicy ${cref.id} references RightSpecification ${apdsId}, which does not exist`);
  }
  merger.add("permit", cref, aref, "cds");
}

function cdsPlace(cref: Ref, apdsId: string, apds: ApdsSnapshot, merger: Merger): void {
  const element = apds.elements.get(apdsId);
  const apdsType = element ? String(element.type || "place") : "place";
  const aref = { type: apdsType, id: apdsId };
  if (cref.type === "CurbPolicy") {
    merger.issue("invalid_reference", cref, aref, "a CurbPolicy may only reference a RightSpecification");
    return;
  }
  if (!element) {
    merger.issue("apds_target_missing", cref, aref, `${cref.type} ${cref.id} references APDS element ${apdsId}, which does not exist`);
  }
  merger.add(apdsType === "vehicularAccess" ? "access" : "supply", cref, aref, "cds");
}

function cdsSide(cds: CdsSnapshot, apds: ApdsSnapshot, merger: Merger): void {
  for (const [cdsType, record] of cdsRecords(cds)) {
    const cdsId = record[CDS_ID_FIELDS[cdsType]];
    if (!isString(cdsId)) continue;
    const cref = { type: cdsType, id: cdsId };
    for (const [collection, apdsId] of apdsReferences(record)) {
      if (!collection) merger.issue("invalid_reference", cref, null, `${cdsType} ${cdsId} has an APDS reference with an unrecognised URL`);
      else if (collection === RIGHT_SPECS) cdsPermit(cref, apdsId, apds, merger);
      else cdsPlace(cref, apdsId, apds, merger);
    }
  }
}

function apdsSide(cds: CdsSnapshot, apds: ApdsSnapshot, merger: Merger): void {
  const known = new Set(cdsRecords(cds).map(([t, r]) => JSON.stringify([t, r[CDS_ID_FIELDS[t]]])));
  const successor = new Map<string, string>();
  for (const zone of cds.zones) {
    if (!isString(zone.curb_zone_id)) continue;
    for (const prev of asArray(zone.prev_curb_zone_ids)) if (isString(prev)) successor.set(prev, zone.curb_zone_id);
  }
  const elements = [...apds.elements.values()].sort((a, b) => cmp(a.id as string, b.id as string));
  for (const element of elements) {
    const ref = element.operatorDefinedReference;
    if (!isObject(ref) || !isString(ref.className) || !(ref.className in CLASSNAME_TO_CDS) || !isString(ref.id)) continue;
    const apdsType = String(element.type || "place");
    const aref = { type: apdsType, id: element.id as string };
    const cdsType = CLASSNAME_TO_CDS[ref.className] as CdsType;
    let cdsId = ref.id;
    if (!known.has(JSON.stringify([cdsType, cdsId]))) {
      const next = cdsType === "CurbZone" ? successor.get(cdsId) : undefined;
      if (next) {
        merger.issue("stale_cds_reference", { type: cdsType, id: cdsId }, aref, `curb zone ${cdsId} was replaced by ${next}`);
        cdsId = next;
      } else {
        merger.issue("cds_target_missing", { type: cdsType, id: cdsId }, aref, `APDS element ${aref.id} references ${cdsType} ${cdsId}, which does not exist`);
        continue;
      }
    }
    merger.add(apdsType === "vehicularAccess" ? "access" : "supply", { type: cdsType, id: cdsId }, aref, "apds");
  }
}

export function buildLinks(cds: CdsSnapshot, apds: ApdsSnapshot): { links: Link[]; issues: Issue[] } {
  const merger = new Merger();
  cdsSide(cds, apds, merger);
  apdsSide(cds, apds, merger);
  return merger.result();
}

function without(map: ReadonlyMap<string, JsonObject>, id: string): Map<string, JsonObject> {
  return new Map([...map].filter(([key]) => key !== id));
}

/** In-memory registry state. Every mutation replaces snapshots and rebuilds links. */
export class Registry {
  cds: CdsSnapshot = emptyCds();
  apds: ApdsSnapshot = apdsSnapshot([], []);
  links: Link[] = [];
  issues: Issue[] = [];
  lastSync: string | null = null;

  constructor(readonly maxEntries: number = MAX_REGISTRY_ENTRIES) {}

  get synced(): boolean {
    return this.lastSync !== null;
  }

  replace(cds: CdsSnapshot, apds: ApdsSnapshot, syncedAt: string): void {
    this.cds = cds;
    this.apds = apds;
    this.lastSync = syncedAt;
    this.rebuild();
  }

  /** Insert or replace an element. Returns false (and changes nothing) if a new id would exceed the cap. */
  upsertElement(element: JsonObject): boolean {
    const id = element.id as string;
    if (!this.apds.elements.has(id) && this.apds.elements.size >= this.maxEntries) return false;
    this.apds = { ...this.apds, elements: new Map([...this.apds.elements, [id, element]]) };
    this.rebuild();
    return true;
  }

  removeElement(id: string): void {
    this.apds = { ...this.apds, elements: without(this.apds.elements, id) };
    this.rebuild();
  }

  /** Insert or replace a RightSpecification. Returns false if a new id would exceed the cap. */
  upsertRightSpec(spec: JsonObject): boolean {
    const id = spec.id as string;
    if (!this.apds.rightSpecs.has(id) && this.apds.rightSpecs.size >= this.maxEntries) return false;
    this.apds = { ...this.apds, rightSpecs: new Map([...this.apds.rightSpecs, [id, spec]]) };
    this.rebuild();
    return true;
  }

  removeRightSpec(id: string): void {
    this.apds = { ...this.apds, rightSpecs: without(this.apds.rightSpecs, id) };
    this.rebuild();
  }

  find(filter: { cdsId?: string; apdsId?: string; kind?: string }): Link[] {
    return this.links.filter(
      (l) =>
        (filter.cdsId === undefined || l.cds.id === filter.cdsId) &&
        (filter.apdsId === undefined || l.apds.id === filter.apdsId) &&
        (filter.kind === undefined || l.kind === filter.kind),
    );
  }

  private rebuild(): void {
    ({ links: this.links, issues: this.issues } = buildLinks(this.cds, this.apds));
  }
}
