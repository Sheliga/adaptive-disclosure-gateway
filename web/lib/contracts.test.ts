import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { describe, expect, it } from "vitest";

import { DISCLOSURE_SUMMARY_STATUSES, KNOWN_DISCLOSURE_OUTCOMES } from "./contracts";

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

/**
 * Same source-on-disk technique as above, for the OTHER closed set the
 * runtime guards depend on. `summary.status` is not merely displayed: it
 * decides whether the confirm-and-send button exists at all, and
 * `lib/responseGuards.ts` rejects any response whose status is outside this
 * set. So a value added to the Python `Literal` and not mirrored here would
 * make the UI reject perfectly valid responses -- and, worse, a value
 * REMOVED from Python and left here would keep a status the API can no
 * longer mean in the set the UI treats as safe to act on.
 */
function readPythonSummaryStatusLiteral(): string[] {
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

  const match = source.match(/status:\s*Literal\[([^\]]+)\]/);
  if (!match) {
    throw new Error(
      "could not locate `status: Literal[...]` in application/contracts.py -- " +
        "has DisclosureSummary.status changed shape?",
    );
  }

  const values = [...match[1].matchAll(/"([a-z_]+)"/g)].map((valueMatch) => valueMatch[1]);
  if (values.length === 0) {
    throw new Error("found the status Literal but extracted zero values -- regex likely stale");
  }
  return values;
}

describe("DISCLOSURE_SUMMARY_STATUSES stays synchronized with Python's status Literal", () => {
  it("has exactly one TypeScript entry per Python literal member", () => {
    const pythonValues = readPythonSummaryStatusLiteral();

    for (const value of pythonValues) {
      expect(DISCLOSURE_SUMMARY_STATUSES).toContain(value);
    }
    for (const value of DISCLOSURE_SUMMARY_STATUSES) {
      expect(pythonValues).toContain(value);
    }

    expect(DISCLOSURE_SUMMARY_STATUSES.length).toBe(pythonValues.length);
  });
});
