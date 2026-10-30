/** T3: shared permit verification (docs/03 §3.4, profile §2.5). Pure functions only. */
import { asArray, cmp, isObject, isString, type JsonObject } from "./json.js";
import { RIGHT_SPECS, apdsReferences } from "./registry.js";

export const CREDENTIAL_TYPES = ["permit", "licensePlate"] as const;
const INACTIVE_STATUSES = new Set(["suspended", "planned"]);
const ISO_INSTANT = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2})(?::(\d{2})(?:\.(\d+))?)?)?(?:Z|([+-])(\d{2}):(\d{2}))?$/;
const MIN_INSTANT = Date.parse("0001-01-01T00:00:00Z");
const MAX_INSTANT = Date.parse("9999-12-31T23:59:59.999Z");

export type Outcome = "valid" | "expired" | "not_yet_valid" | "programme_inactive";

export interface Programme {
  curb_policy_id: string;
  right_specification_id: string;
}

/**
 * Parse an ISO-8601 instant in the profile's strict form to epoch ms; values without an offset are UTC.
 * Returns null if invalid. The accepted form (ISO_INSTANT) and the rules below are identical in the Python
 * implementation: the fields must form a real calendar date and time (no Feb 30, 24:00 or leap second), the
 * offset is below 24:00 with minutes below 60, the UTC instant lies in years 0001-9999, and fractional
 * seconds are truncated to milliseconds.
 */
export function parseInstant(value: string): number | null {
  const match = ISO_INSTANT.exec(value.trim());
  if (!match) return null;
  const field = (i: number): number => Number(match[i] ?? 0);
  const wanted = [field(1), field(2), field(3), field(4), field(5), field(6)];
  const [year, month, day, hour, minute, second] = wanted as [number, number, number, number, number, number];
  const offHours = field(9);
  const offMinutes = field(10);
  if (year < 1 || offHours > 23 || offMinutes > 59) return null;
  const local = new Date(0);
  local.setUTCFullYear(year, month - 1, day);
  local.setUTCHours(hour, minute, second, Number((match[7] ?? "").padEnd(3, "0").slice(0, 3)));
  // Date rolls impossible fields over (Feb 30 becomes Mar 2); reject them instead.
  const actual = [local.getUTCFullYear(), local.getUTCMonth() + 1, local.getUTCDate(), local.getUTCHours(), local.getUTCMinutes(), local.getUTCSeconds()];
  if (actual.some((v, i) => v !== wanted[i])) return null;
  const ms = local.getTime() - (match[8] === "-" ? -1 : 1) * (offHours * 60 + offMinutes) * 60_000;
  return ms >= MIN_INSTANT && ms <= MAX_INSTANT ? ms : null;
}

export const formatInstant = (ms: number): string => new Date(Math.floor(ms / 1000) * 1000).toISOString().replace(".000Z", "Z");
export const normalizeCredential = (value: string): string => value.trim().toUpperCase();
export const compactCredential = (value: string): string => value.toUpperCase().replace(/[ -]/g, "");
export const maskCredential = (value: string): string =>
  value.length <= 6 ? "*".repeat(value.length) : `${value.slice(0, 3)}***${value.slice(-3)}`;

function isPermitRule(rule: unknown): boolean {
  return isObject(rule) && (asArray(rule.user_classes).includes("permit") || asArray(rule.purposes).includes("permit"));
}

export function programmes(policies: readonly JsonObject[]): Programme[] {
  const found = new Map<string, Programme>();
  for (const policy of policies) {
    const policyId = policy.curb_policy_id;
    if (!isString(policyId) || !Array.isArray(policy.rules) || !policy.rules.some(isPermitRule)) continue;
    for (const [collection, specId] of apdsReferences(policy)) {
      if (collection === RIGHT_SPECS) found.set(`${specId}\u0000${policyId}`, { curb_policy_id: policyId, right_specification_id: specId });
    }
  }
  return [...found.values()].sort((a, b) => cmp(a.right_specification_id, b.right_specification_id) || cmp(a.curb_policy_id, b.curb_policy_id));
}

export function holdsCredential(right: JsonObject, credential: string): boolean {
  const holder = right.rightHolder;
  const wanted = compactCredential(credential);
  return asArray(isObject(holder) ? holder.credentials : undefined).some((cred) => {
    const ident = isObject(cred) ? cred.identifier : undefined;
    return isObject(ident) && isString(ident.id) && compactCredential(ident.id) === wanted;
  });
}

const optionalInstant = (value: unknown): number | null => (isString(value) ? parseInstant(value) : null);

/** [present, instant]. A present value that does not parse yields [true, null] so checks fail closed. */
function bound(record: JsonObject, key: string): [boolean, number | null] {
  const value = record[key];
  return value === undefined || value === null ? [false, null] : [true, optionalInstant(value)];
}

export function programmeActive(spec: JsonObject | null | undefined, at: number): boolean {
  const validity = spec?.validity;
  if (!isObject(validity) || INACTIVE_STATUSES.has(String(validity.validityStatus))) return false;
  const period = validity.validityTimeSpecification;
  if (!isObject(period)) return false;
  const start = optionalInstant(period.overallStartTime);
  const [hasEnd, end] = bound(period, "overallEndTime");
  if (start === null || start > at) return false;
  return !hasEnd || (end !== null && at < end);
}

export function evaluate(right: JsonObject, spec: JsonObject | null | undefined, at: number): Outcome {
  const [hasIssued, issued] = bound(right, "issuanceTime");
  const [hasExpiry, expiry] = bound(right, "expiry");
  if (hasIssued && (issued === null || issued > at)) return "not_yet_valid";
  if (hasExpiry && (expiry === null || expiry <= at)) return "expired";
  if (!programmeActive(spec, at)) return "programme_inactive";
  return "valid";
}

/** Latest expiry first (no expiry counts as latest), then id ascending. */
function latestFirst(a: JsonObject, b: JsonObject): number {
  const ea = optionalInstant(a.expiry);
  const eb = optionalInstant(b.expiry);
  if (ea === null && eb !== null) return -1;
  if (eb === null && ea !== null) return 1;
  return (eb ?? 0) - (ea ?? 0) || cmp(String(a.id ?? ""), String(b.id ?? ""));
}

/** Pick the overall result and the deciding AssignedRight (docs/03 §3.4 step 6). */
export function decide(outcomes: ReadonlyArray<readonly [JsonObject, Outcome]>): [Outcome | "not_found", JsonObject | null] {
  if (outcomes.length === 0) return ["not_found", null];
  const valid = outcomes.filter(([, o]) => o === "valid").map(([r]) => r);
  if (valid.length > 0) return ["valid", [...valid].sort(latestFirst)[0] as JsonObject];
  const [right, outcome] = [...outcomes].sort((x, y) => latestFirst(x[0], y[0]))[0] as readonly [JsonObject, Outcome];
  return [outcome, right];
}

export function rightSummary(right: JsonObject | null) {
  return right ? { id: right.id ?? null, version: right.version ?? null, expiry: right.expiry ?? null } : null;
}
