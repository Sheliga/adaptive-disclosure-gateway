import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { BASE_PATH_ENV_VAR, apiPath, normalizeBasePath, prefixWithBasePath, resolveBasePath } from "./basePath";

/**
 * This module runs in Node, where `process.env` is real, so no behavioral
 * test above/below can catch `BASE_PATH` being computed through an
 * indirection (`env[BASE_PATH_ENV_VAR]`, `process.env` captured in a
 * variable, ...) that webpack's DefinePlugin cannot inline into the
 * browser bundle -- see `basePath.ts`'s module docstring. This regressed to
 * production exactly once for that reason: every Vitest test here passed
 * while the shipped bundle silently resolved `BASE_PATH` to `""` in the
 * browser. `check:basepath` (`scripts/check-basepath-inlined.mjs`) is the
 * real regression guard, because it inspects the compiled `.next/static`
 * output; this is a cheap, fast-running companion that pins the one textual
 * property the fix depends on, so a future refactor that reintroduces the
 * indirection fails immediately in `npm test`, not only in the slower
 * build-and-grep check.
 */
describe("BASE_PATH source shape", () => {
  it("computes BASE_PATH from the literal expression process.env.ADG_WEB_BASE_PATH", () => {
    const source = readFileSync(path.join(import.meta.dirname, "basePath.ts"), "utf-8");
    const match = source.match(/export const BASE_PATH = ([^;]+);/);
    expect(match).not.toBeNull();
    expect(match?.[1]).toBe("normalizeBasePath(process.env.ADG_WEB_BASE_PATH)");
  });
});

describe("normalizeBasePath", () => {
  it("returns an empty string when the raw value is undefined", () => {
    expect(normalizeBasePath(undefined)).toBe("");
  });

  it("returns an empty string for an empty or whitespace-only value", () => {
    expect(normalizeBasePath("")).toBe("");
    expect(normalizeBasePath("   ")).toBe("");
  });

  it("returns an empty string for a bare slash", () => {
    expect(normalizeBasePath("/")).toBe("");
  });

  it("adds a leading slash when the raw value omits one", () => {
    expect(normalizeBasePath("disclosure-gateway")).toBe("/disclosure-gateway");
  });

  it("strips a single trailing slash", () => {
    expect(normalizeBasePath("/disclosure-gateway/")).toBe("/disclosure-gateway");
  });

  it("strips repeated trailing slashes", () => {
    expect(normalizeBasePath("/disclosure-gateway///")).toBe("/disclosure-gateway");
  });

  it("trims surrounding whitespace before normalizing", () => {
    expect(normalizeBasePath("  /disclosure-gateway  ")).toBe("/disclosure-gateway");
  });
});

describe("resolveBasePath", () => {
  it("is empty when the env var is absent from the given map", () => {
    expect(resolveBasePath({})).toBe("");
  });

  it("reads ADG_WEB_BASE_PATH out of the given env map", () => {
    expect(resolveBasePath({ [BASE_PATH_ENV_VAR]: "/disclosure-gateway" })).toBe(
      "/disclosure-gateway",
    );
  });

  it("normalizes the value it reads", () => {
    expect(resolveBasePath({ [BASE_PATH_ENV_VAR]: "disclosure-gateway/" })).toBe(
      "/disclosure-gateway",
    );
  });
});

describe("prefixWithBasePath", () => {
  it("returns the path unchanged when basePath is empty", () => {
    expect(prefixWithBasePath("/api/health", "")).toBe("/api/health");
  });

  it("prefixes the path when basePath is set", () => {
    expect(prefixWithBasePath("/api/health", "/disclosure-gateway")).toBe(
      "/disclosure-gateway/api/health",
    );
  });

  it("does not introduce a double slash at the join", () => {
    const result = prefixWithBasePath("/api/health", "/disclosure-gateway");
    expect(result).not.toContain("//");
  });

  it("does not prefix twice on an already-prefixed path", () => {
    const once = prefixWithBasePath("/api/health", "/disclosure-gateway");
    const twice = prefixWithBasePath(once, "/disclosure-gateway");
    expect(twice).toBe(once);
  });

  it("rejects a path that does not start with '/'", () => {
    expect(() => prefixWithBasePath("api/health", "/disclosure-gateway")).toThrow();
  });
});

describe("apiPath", () => {
  it("mirrors prefixWithBasePath against the resolved BASE_PATH (empty in the test environment)", () => {
    expect(apiPath("/api/health")).toBe("/api/health");
  });
});
