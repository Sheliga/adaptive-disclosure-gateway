import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";

import {
  DEMO_VAULT_EXPLORER_ENV_VAR,
  demoVaultExplorerDisabledResponse,
  isDemoVaultExplorerEnabled,
} from "./demoVaultExplorer";

const ORIGINAL_ENV = { ...process.env };

afterEach(() => {
  process.env = { ...ORIGINAL_ENV };
});

/**
 * The flag-parsing rule must be BYTE-IDENTICAL to the Python API's own
 * `application/settings.py::demo_vault_explorer_enabled` -- enabled iff the
 * variable is set AND its stripped value is exactly "1". Any divergence
 * here would let the web gate and the api gate disagree about whether the
 * vault explorer surface is on.
 */
describe("isDemoVaultExplorerEnabled -- full flag table matches the Python parsing rule", () => {
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

  it.each(cases)("ADG_ENABLE_DEMO_VAULT_EXPLORER=%j -> enabled=%s", (value, expected) => {
    const env: Record<string, string | undefined> = {};
    if (value !== undefined) {
      env[DEMO_VAULT_EXPLORER_ENV_VAR] = value;
    }
    expect(isDemoVaultExplorerEnabled(env)).toBe(expected);
  });

  it("reads the real process.env by default", () => {
    delete process.env[DEMO_VAULT_EXPLORER_ENV_VAR];
    expect(isDemoVaultExplorerEnabled()).toBe(false);

    process.env[DEMO_VAULT_EXPLORER_ENV_VAR] = "1";
    expect(isDemoVaultExplorerEnabled()).toBe(true);
  });
});

describe("demoVaultExplorerDisabledResponse", () => {
  it("is a fixed 404 with a fixed, content-free body and no-store headers", async () => {
    const response = demoVaultExplorerDisabledResponse();

    expect(response.status).toBe(404);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(response.headers.get("pragma")).toBe("no-cache");
    const body = await response.json();
    expect(body).toEqual({ detail: "not found", kind: "DemoVaultExplorerDisabled" });
  });
});

/**
 * Drift test: `DEMO_VAULT_EXPLORER_ENV_VAR` here must equal the constant
 * name `application/settings.py` declares -- a hand-typed string on each
 * side that happened to match once but silently diverged later would make
 * the web gate check a different environment variable than the one the
 * Python API (and compose.demo.yaml) actually uses.
 */
describe("DEMO_VAULT_EXPLORER_ENV_VAR stays synchronized with application/settings.py", () => {
  it("matches the Python DEMO_VAULT_EXPLORER_ENV_VAR constant exactly", () => {
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

    const match = source.match(/DEMO_VAULT_EXPLORER_ENV_VAR\s*=\s*"([A-Z_]+)"/);
    if (!match) {
      throw new Error(
        "could not locate `DEMO_VAULT_EXPLORER_ENV_VAR = \"...\"` in application/settings.py -- " +
          "has it been renamed or moved?",
      );
    }

    expect(DEMO_VAULT_EXPLORER_ENV_VAR).toBe(match[1]);
  });
});
