/** Service configuration, read from environment variables (docs/03-link-service.md §3.1). */

export type AuthScheme = "bearer" | "mcc";

export interface Settings {
  readonly cdsBaseUrl: string;
  readonly apdsBaseUrl: string;
  readonly cdsToken?: string;
  readonly apdsToken?: string;
  readonly apdsAuthScheme: AuthScheme;
  readonly webhookToken?: string;
  readonly defaultRadiusM: number;
  readonly httpTimeoutMs: number;
  readonly host: string;
  readonly port: number;
}

type Env = Readonly<Record<string, string | undefined>>;

function baseUrl(env: Env, name: string): string {
  const value = (env[name] ?? "").trim();
  if (!value) throw new Error(`${name} is required`);
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new Error(`${name} must be an absolute http(s) URL`);
  }
  if (!["http:", "https:"].includes(parsed.protocol)) throw new Error(`${name} must be an absolute http(s) URL`);
  return value.replace(/\/+$/, "");
}

function int(env: Env, name: string, fallback: number, lo: number, hi: number): number {
  const raw = env[name];
  if (raw === undefined || raw === "") return fallback;
  if (!/^\d+$/.test(raw.trim())) throw new Error(`${name} must be an integer`);
  const value = Number(raw);
  if (value < lo || value > hi) throw new Error(`${name} must be between ${lo} and ${hi}`);
  return value;
}

function authScheme(env: Env): AuthScheme {
  const value = (env.APDS_AUTH_SCHEME || "bearer").trim().toLowerCase();
  if (value !== "bearer" && value !== "mcc") throw new Error("APDS_AUTH_SCHEME must be one of bearer, mcc");
  return value;
}

function optional(env: Env, name: string): string | undefined {
  return env[name] ? env[name] : undefined;
}

export function settingsFromEnv(env: Env): Settings {
  return {
    cdsBaseUrl: baseUrl(env, "CDS_BASE_URL"),
    apdsBaseUrl: baseUrl(env, "APDS_BASE_URL"),
    cdsToken: optional(env, "CDS_TOKEN"),
    apdsToken: optional(env, "APDS_TOKEN"),
    apdsAuthScheme: authScheme(env),
    webhookToken: optional(env, "LINK_WEBHOOK_TOKEN"),
    defaultRadiusM: int(env, "DEFAULT_RADIUS_M", 400, 1, 5000),
    httpTimeoutMs: int(env, "HTTP_TIMEOUT_MS", 10_000, 100, 120_000),
    host: env.HOST || "0.0.0.0",
    port: int(env, "PORT", 8080, 1, 65_535),
  };
}
