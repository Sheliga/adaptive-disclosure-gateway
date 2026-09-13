import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";

import { DEMO_TRANSPARENCY_ENV_VAR, demoTransparencyDisabledResponse, isDemoTransparencyEnabled } from "./demoTransparency";

const ORIGINAL_ENV = { ...process.env };

afterEach(() => {
  process.env = { ...ORIGINAL_ENV };
});

/**
 * The flag-parsing rule must be BYTE-IDENTICAL to the Python API's own
 * `application/settings.py::demo_transparency_enabled` -- enabled iff the
 * variable is set AND its stripped value is exactly "1". Any divergence
 * here would let the web gate and the api gate disagree about whether the
 * demo transparency surfaces are on, which is exactly the kind of drift
 * that would let one side expose what the other means to keep closed.
 */
describe("isDemoTransparencyEnabled -- full flag table matches the Python parsing rule", () => {
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

/**
 * Drift test: `DEMO_TRANSPARENCY_ENV_VAR` here must equal the constant name
 * `application/settings.py` declares -- a hand-typed string on each side
 * that happened to match once but silently diverged later would make the
 * web gate check a different environment variable than the one the Python
 * API (and compose.demo.yaml) actually uses.
 */
describe("DEMO_TRANSPARENCY_ENV_VAR stays synchronized with application/settings.py", () => {
  it("matches the Python DEMO_TRANSPARENCY_ENV_VAR constant exactly", () => {
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

    const match = source.match(/DEMO_TRANSPARENCY_ENV_VAR\s*=\s*"([A-Z_]+)"/);
    if (!match) {
      throw new Error(
        "could not locate `DEMO_TRANSPARENCY_ENV_VAR = \"...\"` in application/settings.py -- " +
          "has it been renamed or moved?",
      );
    }

    expect(DEMO_TRANSPARENCY_ENV_VAR).toBe(match[1]);
  });
});
