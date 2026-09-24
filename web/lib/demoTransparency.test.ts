import { afterEach, describe, expect, it } from "vitest";

import { DEMO_TRANSPARENCY_ENV_VAR, demoTransparencyDisabledResponse, isDemoTransparencyEnabled } from "./demoTransparency";

const ORIGINAL_ENV = { ...process.env };

afterEach(() => {
  process.env = { ...ORIGINAL_ENV };
});

/**
 * The flag-parsing rule is identical to the other two demo gates
 * (`demoInspection.ts` / `demoVaultExplorer.ts`, and the Python API's own
 * `application/settings.py::demo_inspection_enabled` /
 * `demo_vault_explorer_enabled`) -- enabled iff the variable is set AND its
 * stripped value is exactly "1". The Python API no longer reads
 * `ADG_ENABLE_DEMO_TRANSPARENCY` itself (issue #103); this table pins that
 * this module's own parsing stays exact regardless.
 */
describe("isDemoTransparencyEnabled -- full flag table matches the shared demo-gate parsing rule", () => {
  const cases: [string | undefined, boolean][] = [
    [undefined, false],
    ["", false],
    [" ", false],
    ["0", false],
    ["true", false],
    ["yes", false],
    ["2", false],
    ["1", true],
    [" 1 ", true],
    ["1 ", true],
    [" 1", true],
  ];

  it.each(cases)("ADG_ENABLE_DEMO_TRANSPARENCY=%j -> enabled=%s", (value, expected) => {
    const env: Record<string, string | undefined> = {};
    if (value !== undefined) {
      env[DEMO_TRANSPARENCY_ENV_VAR] = value;
    }
    expect(isDemoTransparencyEnabled(env)).toBe(expected);
  });

  it("reads the real process.env by default", () => {
    delete process.env[DEMO_TRANSPARENCY_ENV_VAR];
    expect(isDemoTransparencyEnabled()).toBe(false);

    process.env[DEMO_TRANSPARENCY_ENV_VAR] = "1";
    expect(isDemoTransparencyEnabled()).toBe(true);
  });
});

describe("demoTransparencyDisabledResponse", () => {
  it("is a fixed 404 with a fixed, content-free body", async () => {
    const response = demoTransparencyDisabledResponse();

    expect(response.status).toBe(404);
    const body = await response.json();
    expect(body).toEqual({ detail: "not found", kind: "DemoTransparencyDisabled" });
  });
});

// No drift test against `application/settings.py` here: since issue #103,
// the Python API no longer reads `ADG_ENABLE_DEMO_TRANSPARENCY` at all (see
// this file's own module docstring, and `demoInspection.ts`'s), so there is
// no Python-side `DEMO_TRANSPARENCY_ENV_VAR` constant left to stay
// synchronized with. `demoInspection.test.ts` and `demoVaultExplorer.test.ts`
// each still carry that drift test for the flags Python does read.
