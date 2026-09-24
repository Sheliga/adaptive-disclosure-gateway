import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";

import { DEMO_INSPECTION_ENV_VAR } from "@/lib/demoInspection";
import { DEMO_TRANSPARENCY_ENV_VAR } from "@/lib/demoTransparency";
import { DEMO_VAULT_EXPLORER_ENV_VAR } from "@/lib/demoVaultExplorer";

import { dynamic, GET } from "./route";

const ORIGINAL_ENV = { ...process.env };

afterEach(() => {
  process.env = { ...ORIGINAL_ENV };
});

function setFlag(name: string, value: string | undefined): void {
  if (value === undefined) {
    delete process.env[name];
  } else {
    process.env[name] = value;
  }
}

describe("GET /api/demo/features", () => {
  it("declares route segment config dynamic = force-dynamic", () => {
    // Otherwise `next build` may prerender this route and bake the
    // build-time env into the image, which is exactly the bug this static
    // pin exists to catch -- see the module docstring.
    expect(dynamic).toBe("force-dynamic");
  });

  it("returns exactly the three-flag key set, nothing more and nothing less", async () => {
    process.env[DEMO_INSPECTION_ENV_VAR] = "1";
    process.env[DEMO_TRANSPARENCY_ENV_VAR] = "1";
    process.env[DEMO_VAULT_EXPLORER_ENV_VAR] = "1";

    const response = await GET();
    const body = await response.json();

    expect(Object.keys(body).sort()).toEqual(
      ["demo_inspection_enabled", "demo_transparency_enabled", "demo_vault_explorer_enabled"].sort(),
    );
  });

  /**
   * Each of the three capabilities is independently gated server-side by
   * its own env var; none implies another. This matrix pins that every one
   * of the 8 on/off combinations reports each flag from its own variable
   * only -- a defect that derived one flag from another (e.g. transparency
   * implying inspection, as the endpoint used to suggest in prose before
   * issue #103) would flip one of these off-diagonal cells and fail here.
   */
  const BOOL_COMBOS: [boolean, boolean, boolean][] = [
    [false, false, false],
    [true, false, false],
    [false, true, false],
    [false, false, true],
    [true, true, false],
    [true, false, true],
    [false, true, true],
    [true, true, true],
  ];

  it.each(BOOL_COMBOS)(
    "inspection=%s transparency=%s vaultExplorer=%s -> each flag reported from its own variable only",
    async (inspection, transparency, vaultExplorer) => {
      setFlag(DEMO_INSPECTION_ENV_VAR, inspection ? "1" : undefined);
      setFlag(DEMO_TRANSPARENCY_ENV_VAR, transparency ? "1" : undefined);
      setFlag(DEMO_VAULT_EXPLORER_ENV_VAR, vaultExplorer ? "1" : undefined);

      const response = await GET();

      expect(response.status).toBe(200);
      expect(await response.json()).toEqual({
        demo_inspection_enabled: inspection,
        demo_transparency_enabled: transparency,
        demo_vault_explorer_enabled: vaultExplorer,
      });
    },
  );

  it.each([
    ["true", false],
    ["yes", false],
    ["0", false],
    ["", false],
    [" 1 ", true],
  ] as const)(
    "applies strict parsing to demo_inspection_enabled: %j -> %s",
    async (value, expected) => {
      process.env[DEMO_INSPECTION_ENV_VAR] = value;
      delete process.env[DEMO_TRANSPARENCY_ENV_VAR];
      delete process.env[DEMO_VAULT_EXPLORER_ENV_VAR];

      const response = await GET();

      expect((await response.json()).demo_inspection_enabled).toBe(expected);
    },
  );

  it("public production posture: only ADG_ENABLE_DEMO_INSPECTION=1 set -> {true, false, false}", async () => {
    process.env[DEMO_INSPECTION_ENV_VAR] = "1";
    delete process.env[DEMO_TRANSPARENCY_ENV_VAR];
    delete process.env[DEMO_VAULT_EXPLORER_ENV_VAR];

    const response = await GET();

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({
      demo_inspection_enabled: true,
      demo_transparency_enabled: false,
      demo_vault_explorer_enabled: false,
    });
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
