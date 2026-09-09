import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { describe, expect, it } from "vitest";

import { KNOWN_DISCLOSURE_OUTCOMES } from "./contracts";

/**
 * Reads the Python `DisclosureOutcome` StrEnum's own declared values
 * directly from `application/contracts.py` on disk. This is a repo-relative
 * read (not an import) precisely so this test does not depend on Python
 * being installed/runnable in the environment this test suite runs in --
 * it only needs the source file's text.
 */
function readPythonDisclosureOutcomeValues(): string[] {
  const here = path.dirname(fileURLToPath(import.meta.url));
  const contractsPath = path.resolve(
    here,
    "..",
    "..",
    "src",
    "adaptive_disclosure_gateway",
    "application",
    "contracts.py",
  );
  const source = readFileSync(contractsPath, "utf-8");

  const classMatch = source.match(
    /class DisclosureOutcome\(StrEnum\):[\s\S]*?(?=\nclass |$)/,
  );
  if (!classMatch) {
    throw new Error(
      "could not locate `class DisclosureOutcome(StrEnum):` block in application/contracts.py -- " +
        "has it been renamed or moved?",
    );
  }
  const block = classMatch[0];

  const values = [...block.matchAll(/=\s*"([a-z_]+)"/g)].map((match) => match[1]);
  if (values.length === 0) {
    throw new Error(
      "found the DisclosureOutcome block but extracted zero string values -- regex likely stale",
    );
  }
  return values;
}

describe("KNOWN_DISCLOSURE_OUTCOMES stays synchronized with Python's DisclosureOutcome", () => {
  it("has exactly one TypeScript entry per Python enum member", () => {
    const pythonValues = readPythonDisclosureOutcomeValues();

    // Every Python-declared outcome must have a TypeScript counterpart --
    // this is the direction that matters for the no-leak/fail-closed
    // contract: a NEW outcome added on the Python side must fail this test
    // instead of silently reaching the UI as an unrecognized string.
    for (const value of pythonValues) {
      expect(KNOWN_DISCLOSURE_OUTCOMES).toContain(value);
    }

    // And the TypeScript side must not declare a "known" outcome the
    // Python side doesn't actually have -- that would let the fail-closed
    // mapping in outcomes.ts treat a nonexistent code as safe/known.
    for (const value of KNOWN_DISCLOSURE_OUTCOMES) {
      expect(pythonValues).toContain(value);
    }

    expect(KNOWN_DISCLOSURE_OUTCOMES.length).toBe(pythonValues.length);
  });
});
