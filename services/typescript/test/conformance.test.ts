/** Runs the shared conformance suite (conformance/cases.json) against the TypeScript service. */
import { describe, expect, it } from "vitest";
import { buildApp } from "../src/app.js";
import { settingsFromEnv } from "../src/config.js";
import { CASES, FIXTURES, FakeUpstream } from "./fake-upstream.js";

const FIXED_NOW = Date.parse("2026-06-01T12:00:00Z");

export function subsetMatch(expected: unknown, actual: unknown, path = "$"): string[] {
  if (expected === "<any>") return [];
  if (Array.isArray(expected)) {
    if (!Array.isArray(actual) || actual.length !== expected.length) {
      return [`${path}: expected list of ${expected.length}, got ${JSON.stringify(actual)}`];
    }
    return expected.flatMap((e, i) => subsetMatch(e, actual[i], `${path}[${i}]`));
  }
  if (typeof expected === "object" && expected !== null) {
    if (typeof actual !== "object" || actual === null || Array.isArray(actual)) {
      return [`${path}: expected object, got ${JSON.stringify(actual)}`];
    }
    return Object.entries(expected).flatMap(([key, value]) =>
      key in actual ? subsetMatch(value, (actual as Record<string, unknown>)[key], `${path}.${key}`) : [`${path}.${key}: missing`],
    );
  }
  return expected === actual ? [] : [`${path}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`];
}

describe("conformance", () => {
  for (const testCase of CASES) {
    it(testCase.name, async () => {
      const upstream = new FakeUpstream();
      const app = buildApp(settingsFromEnv(FIXTURES.config), { fetch: upstream.fetch, clock: () => FIXED_NOW });
      try {
        for (const [index, step] of testCase.steps.entries()) {
          const req = step.request;
          const resp = await app.inject({ method: req.method, url: req.path, headers: req.headers ?? {}, payload: req.body });
          const label = `step ${index}: ${req.method} ${req.path}`;
          expect(resp.statusCode, `${label}: ${resp.body}`).toBe(step.expect.status);
          expect(subsetMatch(step.expect.body, resp.json()), label).toEqual([]);
        }
      } finally {
        await app.close();
      }
    });
  }
});

describe("subsetMatch", () => {
  it("reports mismatches", () => {
    expect(subsetMatch({ a: [1, { b: 2 }] }, { a: [1, { b: 2, c: 3 }], z: 0 })).toEqual([]);
    expect(subsetMatch({ a: 1 }, {})).toEqual(["$.a: missing"]);
    expect(subsetMatch([1], [1, 2])).not.toEqual([]);
    expect(subsetMatch({ a: "<any>" }, { a: null })).toEqual([]);
  });
});
