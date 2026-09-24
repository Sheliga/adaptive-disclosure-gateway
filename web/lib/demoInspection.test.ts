import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";

import { DEMO_INSPECTION_ENV_VAR, isDemoInspectionEnabled } from "./demoInspection";
import { DEMO_TRANSPARENCY_ENV_VAR } from "./demoTransparency";
import { DEMO_VAULT_EXPLORER_ENV_VAR } from "./demoVaultExplorer";

const ORIGINAL_ENV = { ...process.env };

afterEach(() => {
  process.env = { ...ORIGINAL_ENV };
});

/**
 * The flag-parsing rule must be BYTE-IDENTICAL to the Python API's own
 * `application/settings.py::demo_inspection_enabled` -- enabled iff the
 * variable is set AND its stripped value is exactly "1". Any divergence
 * here would let the web-visible UX signal and the api's actual gate
 * disagree about whether inspection is on.
 */
describe("isDemoInspectionEnabled -- full flag table matches the Python parsing rule", () => {
  const cases: [string | undefined, boolean][] = [
    [undefined, false],
    ["", false],
    [" ", false],
    ["0", false],
    ["true", false],
    ["yes", false],
    ["True", false],
    ["on", false],
    ["2", false],
    ["11", false],
    ["1", true],
    [" 1 ", true],
    ["1 ", true],
    [" 1", true],
  ];

  it.each(cases)("ADG_ENABLE_DEMO_INSPECTION=%j -> enabled=%s", (value, expected) => {
    const env: Record<string, string | undefined> = {};
    if (value !== undefined) {
      env[DEMO_INSPECTION_ENV_VAR] = value;
    }
    expect(isDemoInspectionEnabled(env)).toBe(expected);
  });

  it("reads the real process.env by default", () => {
    delete process.env[DEMO_INSPECTION_ENV_VAR];
    expect(isDemoInspectionEnabled()).toBe(false);

    process.env[DEMO_INSPECTION_ENV_VAR] = "1";
    expect(isDemoInspectionEnabled()).toBe(true);
  });

  it("is not implied by either of the other two demo gates being on", () => {
    delete process.env[DEMO_INSPECTION_ENV_VAR];
    process.env[DEMO_TRANSPARENCY_ENV_VAR] = "1";
    process.env[DEMO_VAULT_EXPLORER_ENV_VAR] = "1";

    expect(isDemoInspectionEnabled()).toBe(false);
  });
});

/**
 * Drift test: `DEMO_INSPECTION_ENV_VAR` here must equal the constant name
 * `application/settings.py` declares -- a hand-typed string on each side
 * that happened to match once but silently diverged later would make the
 * web-visible UX signal and the Python API's own gate disagree about which
 * environment variable controls inspection.
 */
describe("DEMO_INSPECTION_ENV_VAR stays synchronized with application/settings.py", () => {
  it("matches the Python DEMO_INSPECTION_ENV_VAR constant exactly", () => {
    const here = path.dirname(fileURLToPath(import.meta.url));
    const settingsPath = path.resolve(
      here,
      "..",
      "..",
      "src",
      "adaptive_disclosure_gateway",
      "application",
      "settings.py",
    );
    const source = readFileSync(settingsPath, "utf-8");

    const match = source.match(/DEMO_INSPECTION_ENV_VAR\s*=\s*"([A-Z_]+)"/);
    if (!match) {
      throw new Error(
        "could not locate `DEMO_INSPECTION_ENV_VAR = \"...\"` in application/settings.py -- " +
          "has it been renamed or moved?",
      );
    }

    expect(DEMO_INSPECTION_ENV_VAR).toBe(match[1]);
  });
});
