import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";

import { DEMO_TRANSPARENCY_ENV_VAR } from "@/lib/demoTransparency";

import { dynamic, GET } from "./route";

const ORIGINAL_ENV = { ...process.env };

afterEach(() => {
  process.env = { ...ORIGINAL_ENV };
});

describe("GET /api/demo/features", () => {
  it("declares route segment config dynamic = force-dynamic", () => {
    // Otherwise `next build` may prerender this route and bake the
    // build-time env into the image, which is exactly the bug this static
    // pin exists to catch -- see the module docstring.
    expect(dynamic).toBe("force-dynamic");
  });

  it("reports demo_transparency_enabled: false when the flag is unset", async () => {
    delete process.env[DEMO_TRANSPARENCY_ENV_VAR];

    const response = await GET();

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ demo_transparency_enabled: false });
  });

  it("reports demo_transparency_enabled: true when the flag is exactly \"1\"", async () => {
    process.env[DEMO_TRANSPARENCY_ENV_VAR] = "1";

    const response = await GET();

    expect(await response.json()).toEqual({ demo_transparency_enabled: true });
  });

  it("reports false for a near-miss value like \"true\"", async () => {
    process.env[DEMO_TRANSPARENCY_ENV_VAR] = "true";

    const response = await GET();

    expect(await response.json()).toEqual({ demo_transparency_enabled: false });
  });

  it("never returns any field beyond demo_transparency_enabled", async () => {
    process.env[DEMO_TRANSPARENCY_ENV_VAR] = "1";

    const response = await GET();
    const body = await response.json();

    expect(Object.keys(body)).toEqual(["demo_transparency_enabled"]);
  });
});

/**
 * Static text pin: `dynamic = "force-dynamic"` must appear as a genuine
 * Next.js route segment config export in the compiled source, not merely as
 * a value the test file happens to import successfully (which could also
 * be true of an accidental local variable of the same name).
 */
describe("route.ts declares the route segment config textually", () => {
  it("exports `dynamic` as a top-level const named exactly `dynamic`", () => {
    const here = path.dirname(fileURLToPath(import.meta.url));
    const source = readFileSync(path.resolve(here, "route.ts"), "utf-8");

    expect(source).toMatch(/export const dynamic = ["']force-dynamic["'];/);
  });
});
