import { afterEach, describe, expect, it, vi } from "vitest";

/**
 * next.config.ts must derive Next.js's `basePath` (and the `env` value it
 * re-exposes to the client bundle) from `ADG_WEB_BASE_PATH` at module-load
 * time -- Next.js itself requires `basePath` to be known at build time, so
 * this cannot be a runtime lookup. Each test mutates `process.env` directly
 * and forces a fresh module evaluation via `vi.resetModules()` +
 * `await import(...)`, since the config module reads `process.env` at its
 * top level exactly once per load.
 */

const ENV_VAR = "ADG_WEB_BASE_PATH";

describe("next.config.ts basePath derivation", () => {
  const original = process.env[ENV_VAR];

  afterEach(() => {
    if (original === undefined) {
      delete process.env[ENV_VAR];
    } else {
      process.env[ENV_VAR] = original;
    }
    vi.resetModules();
  });

  it("defaults to the root path when ADG_WEB_BASE_PATH is unset", async () => {
    delete process.env[ENV_VAR];
    vi.resetModules();
    const { default: nextConfig } = await import("./next.config");
    expect(nextConfig.basePath).toBe("");
    expect(nextConfig.env?.[ENV_VAR]).toBe("");
  });

  it("derives a normalized basePath when ADG_WEB_BASE_PATH is set", async () => {
    process.env[ENV_VAR] = "disclosure-gateway/";
    vi.resetModules();
    const { default: nextConfig } = await import("./next.config");
    expect(nextConfig.basePath).toBe("/disclosure-gateway");
    expect(nextConfig.env?.[ENV_VAR]).toBe("/disclosure-gateway");
  });
});
