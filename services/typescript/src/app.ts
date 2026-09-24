/** HTTP API of the link service (docs/03-link-service.md §3.4). */
import { timingSafeEqual } from "node:crypto";
import Fastify, { LogController, type FastifyInstance, type FastifyReply, type FastifyRequest } from "fastify";
import type { Settings } from "./config.js";
import { ServiceError, invalidRequest, unauthorized } from "./errors.js";
import { isObject, isString, type JsonObject } from "./json.js";
import * as permits from "./permits.js";
import { LINK_KINDS, type Issue, type Link } from "./registry.js";
import { LinkService } from "./service.js";
import type { FetchLike } from "./upstream.js";

const APDS_EVENT_TYPES = new Set(
  ["AssignedRight", "Session", "Place", "RightSpecification", "Rate", "Organisation"].flatMap((entity) =>
    ["Created", "Updated", "Deleted"].map((action) => `${entity}${action}`),
  ),
);

export interface AppOptions {
  fetch?: FetchLike;
  clock?: () => number;
  logger?: boolean;
  /** Cap on registry entries accepted via webhooks (defaults to MAX_REGISTRY_ENTRIES). */
  maxRegistryEntries?: number;
}

const ok = (reply: FastifyReply, data: unknown) => reply.send({ success: true, data, error: null });
const fail = (reply: FastifyReply, status: number, code: string, message: string) =>
  reply.status(status).send({ success: false, data: null, error: { code, message } });

const linkJson = (l: Link) => ({ kind: l.kind, status: l.status, cds: l.cds, apds: l.apds });
const issueJson = (i: Issue) => ({ code: i.code, cds: i.cds, apds: i.apds, detail: i.detail });

function queryString(request: FastifyRequest, name: string): string | undefined {
  const value = (request.query as Record<string, unknown>)[name];
  if (value === undefined) return undefined;
  if (!isString(value)) throw invalidRequest(`${name} must be given once`);
  return value;
}

function parseRadius(raw: string | undefined, fallback: number): number {
  if (raw === undefined) return fallback;
  if (!/^[0-9]{1,4}$/.test(raw) || Number(raw) < 1 || Number(raw) > 5000) {
    throw invalidRequest("radius_m must be an integer from 1 to 5000");
  }
  return Number(raw);
}

function jsonObject(body: unknown): JsonObject {
  if (!isObject(body)) throw invalidRequest("request body must be a JSON object");
  return body;
}

function permitRequest(body: JsonObject, clock: () => number) {
  const { curb_zone_id: zoneId, credential, credential_type: credentialType, at } = body;
  if (!isString(zoneId) || !zoneId.trim()) throw invalidRequest("curb_zone_id is required");
  if (!isString(credential) || !credential.trim()) throw invalidRequest("credential is required");
  if (credentialType !== undefined && credentialType !== null && !(permits.CREDENTIAL_TYPES as readonly unknown[]).includes(credentialType)) {
    throw invalidRequest("credential_type must be 'permit' or 'licensePlate'");
  }
  let instant = clock();
  if (at !== undefined && at !== null) {
    const parsed = isString(at) ? permits.parseInstant(at) : null;
    if (parsed === null) throw invalidRequest("at must be an ISO-8601 instant");
    instant = parsed;
  }
  return {
    zoneId: zoneId.trim(),
    credential: permits.normalizeCredential(credential),
    credentialType: (credentialType ?? undefined) as string | undefined,
    at: instant,
  };
}

function checkWebhookToken(request: FastifyRequest, expected: string | undefined): void {
  if (!expected) return;
  const presented = request.headers["x-link-webhook-token"];
  const a = Buffer.from(isString(presented) ? presented : "");
  const b = Buffer.from(expected);
  if (a.length !== b.length || !timingSafeEqual(a, b)) throw unauthorized("missing or invalid webhook token");
}

export function buildApp(settings: Settings, options: AppOptions = {}): FastifyInstance {
  const clock = options.clock ?? (() => Date.now());
  const service = new LinkService(settings, options.fetch ?? fetch, clock, options.maxRegistryEntries);
  // Request logging is off: request lines can carry identifiers that must not be logged.
  const app = Fastify({
    logger: options.logger ?? false,
    logController: new LogController({ disableRequestLogging: true }),
  });

  app.setErrorHandler((err, request, reply) => {
    if (err instanceof ServiceError) {
      if (err.status >= 500) request.log.warn(`upstream failure: ${err.message}`);
      return fail(reply, err.status, err.code, err.message);
    }
    const status = (err as { statusCode?: number }).statusCode;
    if (status !== undefined && status >= 400 && status < 500) return fail(reply, 400, "invalid_request", "invalid request");
    request.log.error(`unexpected error: ${(err as Error).name}`);
    return fail(reply, 500, "internal_error", "internal error");
  });
  app.setNotFoundHandler((_, reply) => fail(reply, 404, "not_found", "route not found"));

  app.get("/health", async (_, reply) => {
    const reg = service.registry;
    return ok(reply, { status: "ok", links: reg.links.length, last_sync: reg.lastSync });
  });

  app.post("/sync", async (_, reply) => {
    await service.sync();
    const reg = service.registry;
    return ok(reply, { links: reg.links.map(linkJson), issues: reg.issues.map(issueJson), synced_at: reg.lastSync });
  });

  app.get("/links", async (request, reply) => {
    const kind = queryString(request, "kind");
    if (kind !== undefined && !(LINK_KINDS as readonly string[]).includes(kind)) {
      throw invalidRequest(`kind must be one of ${LINK_KINDS.join(", ")}`);
    }
    const cdsId = queryString(request, "cds_id");
    const apdsId = queryString(request, "apds_id");
    await service.ensureSynced();
    return ok(reply, service.registry.find({ cdsId, apdsId, kind }).map(linkJson));
  });

  app.get("/issues", async (_, reply) => {
    await service.ensureSynced();
    return ok(reply, service.registry.issues.map(issueJson));
  });

  app.get<{ Params: { zoneId: string } }>("/zones/:zoneId/off-street", async (request, reply) => {
    const radius = parseRadius(queryString(request, "radius_m"), settings.defaultRadiusM);
    return ok(reply, await service.offStreet(request.params.zoneId, radius));
  });

  app.post("/permits/verify", async (request, reply) => {
    const req = permitRequest(jsonObject(request.body), clock);
    return ok(reply, await service.verifyPermit(req.zoneId, req.credential, req.credentialType, req.at));
  });

  app.post("/webhooks/apds", async (request, reply) => {
    checkWebhookToken(request, settings.webhookToken);
    const eventType = request.headers["x-apds-event-type"];
    if (!isString(eventType) || !APDS_EVENT_TYPES.has(eventType)) {
      throw invalidRequest("X-APDS-Event-Type header is missing or not an APDS EventTypeEnum value");
    }
    const body = jsonObject(request.body);
    if (!isString(body.id) || !body.id) throw invalidRequest("event data must include an id");
    const applied = await service.applyWebhook(eventType, body);
    return ok(reply, { event_type: eventType, applied });
  });

  return app;
}
