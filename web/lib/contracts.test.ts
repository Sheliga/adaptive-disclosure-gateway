import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { describe, expect, it } from "vitest";

import {
  CANONICAL_COMPARISON_ORDER,
  CANONICAL_COMPARISON_TREATMENTS,
  DISCLOSURE_SUMMARY_STATUSES,
  KNOWN_DISCLOSURE_OUTCOMES,
  KNOWN_INSPECTION_ACTIONS,
  KNOWN_VAULT_SCOPES,
} from "./contracts";

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

/**
 * Pins `CANONICAL_COMPARISON_ORDER` against `application/contracts.py`'s
 * tuple of the same name -- both the SET of strategies and their ORDER.
 * `service.compare_strategies` iterates that Python tuple, and only that
 * tuple, to decide `CompareResponse.entries` order (T21/#29's "canonical
 * order is preserved" requirement); a UI constant that silently drifted
 * from it (member added/removed/reordered) would make the "always
 * DIRECT -> STATIC_SANITIZATION -> REVERSIBLE_PSEUDONYMIZATION ->
 * TASK_AWARE -> POLICY_GOVERNED" claim this module's docstring makes false
 * without any test catching it.
 */
function readPythonCanonicalComparisonOrder(): string[] {
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

  const enumMatch = source.match(/class DisclosureStrategy\(StrEnum\):[\s\S]*?(?=\nclass |\n_STRATEGY_TO_TREATMENT)/);
  if (!enumMatch) {
    throw new Error(
      "could not locate `class DisclosureStrategy(StrEnum):` block in application/contracts.py -- " +
        "has it been renamed or moved?",
    );
  }
  const memberToValue = new Map<string, string>();
  for (const match of enumMatch[0].matchAll(/^ {4}([A-Z_]+)\s*=\s*"([a-z0-9_]+)"/gm)) {
    memberToValue.set(match[1], match[2]);
  }
  if (memberToValue.size === 0) {
    throw new Error(
      "found the DisclosureStrategy block but extracted zero members -- regex likely stale",
    );
  }

  const orderMatch = source.match(
    /CANONICAL_COMPARISON_ORDER:\s*tuple\[DisclosureStrategy, \.\.\.\]\s*=\s*\(([\s\S]*?)\)/,
  );
  if (!orderMatch) {
    throw new Error(
      "could not locate `CANONICAL_COMPARISON_ORDER: tuple[DisclosureStrategy, ...] = (...)` in " +
        "application/contracts.py -- has it been renamed or moved?",
    );
  }
  const members = [...orderMatch[1].matchAll(/DisclosureStrategy\.([A-Z_]+)/g)].map(
    (match) => match[1],
  );
  if (members.length === 0) {
    throw new Error(
      "found CANONICAL_COMPARISON_ORDER but extracted zero members -- regex likely stale",
    );
  }

  return members.map((member) => {
    const value = memberToValue.get(member);
    if (value === undefined) {
      throw new Error(`CANONICAL_COMPARISON_ORDER references unknown DisclosureStrategy member ${member}`);
    }
    return value;
  });
}

describe("CANONICAL_COMPARISON_ORDER stays synchronized with Python's tuple of the same name", () => {
  it("has the exact same strategy codes in the exact same order", () => {
    const pythonOrder = readPythonCanonicalComparisonOrder();

    expect(CANONICAL_COMPARISON_ORDER).toEqual(pythonOrder);
  });
});

/**
 * Derives, independently, the treatment CODE `application/contracts.py`'s
 * `resolve_treatment` maps each canonical strategy to -- by reading
 * `_STRATEGY_TO_TREATMENT` off `contracts.py` and `Treatment`'s own
 * member -> code mapping off `domain.py` -- rather than assuming (as
 * `contracts.ts`'s `CANONICAL_COMPARISON_TREATMENTS` does) that a
 * strategy's own `b0`-`b4` code IS the treatment code it resolves to.
 * CLAUDE.md explicitly warns against treating "treatment equals strategy"
 * as given rather than verified; this is that verification made durable --
 * if `_STRATEGY_TO_TREATMENT` ever mapped one of the five canonical
 * strategies to a differently-coded treatment, this is what would notice,
 * because it never reads `CANONICAL_COMPARISON_TREATMENTS` itself.
 */
function readPythonCanonicalComparisonTreatmentCodes(): string[] {
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
  const domainPath = path.resolve(here, "..", "..", "src", "adaptive_disclosure_gateway", "domain.py");
  const contractsSource = readFileSync(contractsPath, "utf-8");
  const domainSource = readFileSync(domainPath, "utf-8");

  const strategyEnumMatch = contractsSource.match(
    /class DisclosureStrategy\(StrEnum\):[\s\S]*?(?=\nclass |\n_STRATEGY_TO_TREATMENT)/,
  );
  if (!strategyEnumMatch) {
    throw new Error(
      "could not locate `class DisclosureStrategy(StrEnum):` block in application/contracts.py -- " +
        "has it been renamed or moved?",
    );
  }
  const strategyMembers = new Set(
    [...strategyEnumMatch[0].matchAll(/^ {4}([A-Z_]+)\s*=\s*"([a-z0-9_]+)"/gm)].map((match) => match[1]),
  );
  if (strategyMembers.size === 0) {
    throw new Error(
      "found the DisclosureStrategy block but extracted zero members -- regex likely stale",
    );
  }

  const treatmentEnumMatch = domainSource.match(/class Treatment\(StrEnum\):[\s\S]*?(?=\nclass )/);
  if (!treatmentEnumMatch) {
    throw new Error(
      "could not locate `class Treatment(StrEnum):` block in domain.py -- has it been renamed or moved?",
    );
  }
  const treatmentMemberToCode = new Map<string, string>();
  for (const match of treatmentEnumMatch[0].matchAll(/^ {4}([A-Z_]+)\s*=\s*"([a-z0-9_]+)"/gm)) {
    treatmentMemberToCode.set(match[1], match[2]);
  }
  if (treatmentMemberToCode.size === 0) {
    throw new Error("found the Treatment block but extracted zero members -- regex likely stale");
  }

  const mappingMatch = contractsSource.match(
    /_STRATEGY_TO_TREATMENT:\s*dict\[DisclosureStrategy, Treatment\]\s*=\s*\{([\s\S]*?)\n\}/,
  );
  if (!mappingMatch) {
    throw new Error(
      "could not locate `_STRATEGY_TO_TREATMENT: dict[DisclosureStrategy, Treatment] = {...}` in " +
        "application/contracts.py -- has it been renamed or moved?",
    );
  }
  const strategyMemberToTreatmentMember = new Map<string, string>();
  for (const match of mappingMatch[1].matchAll(/DisclosureStrategy\.([A-Z_]+)\s*:\s*Treatment\.([A-Z_]+)/g)) {
    strategyMemberToTreatmentMember.set(match[1], match[2]);
  }
  if (strategyMemberToTreatmentMember.size === 0) {
    throw new Error(
      "found _STRATEGY_TO_TREATMENT but extracted zero entries -- regex likely stale",
    );
  }

  const orderMatch = contractsSource.match(
    /CANONICAL_COMPARISON_ORDER:\s*tuple\[DisclosureStrategy, \.\.\.\]\s*=\s*\(([\s\S]*?)\)/,
  );
  if (!orderMatch) {
    throw new Error(
      "could not locate `CANONICAL_COMPARISON_ORDER: tuple[DisclosureStrategy, ...] = (...)` in " +
        "application/contracts.py -- has it been renamed or moved?",
    );
  }
  const orderedStrategyMembers = [...orderMatch[1].matchAll(/DisclosureStrategy\.([A-Z_]+)/g)].map(
    (match) => match[1],
  );
  if (orderedStrategyMembers.length === 0) {
    throw new Error(
      "found CANONICAL_COMPARISON_ORDER but extracted zero members -- regex likely stale",
    );
  }

  return orderedStrategyMembers.map((strategyMember) => {
    if (!strategyMembers.has(strategyMember)) {
      throw new Error(
        `CANONICAL_COMPARISON_ORDER references unknown DisclosureStrategy member ${strategyMember}`,
      );
    }
    const treatmentMember = strategyMemberToTreatmentMember.get(strategyMember);
    if (treatmentMember === undefined) {
      throw new Error(`_STRATEGY_TO_TREATMENT has no entry for DisclosureStrategy.${strategyMember}`);
    }
    const treatmentCode = treatmentMemberToCode.get(treatmentMember);
    if (treatmentCode === undefined) {
      throw new Error(`Treatment has no member named ${treatmentMember}`);
    }
    return treatmentCode;
  });
}

/**
 * Reads `domain.py`'s `DisclosureAction` StrEnum values directly off disk,
 * the same repo-relative technique as the other drift tests above. Unlike
 * `KNOWN_DISCLOSURE_OUTCOMES`'s pin (an exact set match both ways),
 * `KNOWN_INSPECTION_ACTIONS` is a deliberate SUBSET of `DisclosureAction`:
 * `block_request` and `task_dependent` are real enum members but never the
 * `action` of an actual per-span `Transformation` the inspector projects
 * (see `contracts.ts`'s docstring on `KNOWN_INSPECTION_ACTIONS`) -- so this
 * only asserts the four transformation actions exist there and that
 * `KNOWN_INSPECTION_ACTIONS` contains nothing Python does not.
 */
function readPythonDisclosureActionValues(): string[] {
  const here = path.dirname(fileURLToPath(import.meta.url));
  const domainPath = path.resolve(here, "..", "..", "src", "adaptive_disclosure_gateway", "domain.py");
  const source = readFileSync(domainPath, "utf-8");

  const classMatch = source.match(/class DisclosureAction\(StrEnum\):[\s\S]*?(?=\nclass )/);
  if (!classMatch) {
    throw new Error(
      "could not locate `class DisclosureAction(StrEnum):` block in domain.py -- " +
        "has it been renamed or moved?",
    );
  }
  const values = [...classMatch[0].matchAll(/=\s*"([a-z_]+)"/g)].map((match) => match[1]);
  if (values.length === 0) {
    throw new Error(
      "found the DisclosureAction block but extracted zero string values -- regex likely stale",
    );
  }
  return values;
}

describe("KNOWN_INSPECTION_ACTIONS stays synchronized with Python's DisclosureAction", () => {
  it("contains exactly preserve/pseudonymize/generalize/remove, all real DisclosureAction members", () => {
    const pythonValues = readPythonDisclosureActionValues();

    expect(KNOWN_INSPECTION_ACTIONS).toEqual(["preserve", "pseudonymize", "generalize", "remove"]);
    for (const value of KNOWN_INSPECTION_ACTIONS) {
      expect(pythonValues).toContain(value);
    }
  });

  it("never includes block_request or task_dependent -- neither is a real per-span transformation action", () => {
    expect(KNOWN_INSPECTION_ACTIONS).not.toContain("block_request");
    expect(KNOWN_INSPECTION_ACTIONS).not.toContain("task_dependent");
  });
});

describe("CANONICAL_COMPARISON_TREATMENTS stays synchronized with Python's resolve_treatment", () => {
  it("has the exact treatment code resolve_treatment maps each canonical strategy to, in order", () => {
    // This is derived from `_STRATEGY_TO_TREATMENT` and `Treatment`
    // independently of `CANONICAL_COMPARISON_ORDER`/`readPythonCanonicalComparisonOrder`
    // above, so it cannot pass merely because both sides happen to read the
    // same already-correct constant.
    const pythonTreatments = readPythonCanonicalComparisonTreatmentCodes();

    expect(CANONICAL_COMPARISON_TREATMENTS).toEqual(pythonTreatments);
  });
});

/**
 * T29 / issue #72 drift test: `KNOWN_VAULT_SCOPES` must be a SUBSET of
 * `domain.py`'s `PseudonymScope` member values -- checked in one direction
 * only, deliberately. The vault explorer's own contract excludes
 * `"organization"` on purpose (`PreviewResponse.vault_explorer_token` is
 * never issued for that scope), so this test must not fail merely because
 * Python declares a scope this UI does not expect to ever see from this
 * endpoint; it exists to catch the OTHER drift -- a scope this UI treats as
 * known that Python does not actually declare, or a real request/document/
 * session member renamed on the Python side without this file noticing.
 */
function readPythonPseudonymScopeValues(): string[] {
  const here = path.dirname(fileURLToPath(import.meta.url));
  const domainPath = path.resolve(here, "..", "..", "src", "adaptive_disclosure_gateway", "domain.py");
  const source = readFileSync(domainPath, "utf-8");

  const classMatch = source.match(/class PseudonymScope\(StrEnum\):[\s\S]*?(?=\nclass |$)/);
  if (!classMatch) {
    throw new Error(
      "could not locate `class PseudonymScope(StrEnum):` block in domain.py -- " +
        "has it been renamed or moved?",
    );
  }
  const values = [...classMatch[0].matchAll(/=\s*"([a-z_]+)"/g)].map((match) => match[1]);
  if (values.length === 0) {
    throw new Error(
      "found the PseudonymScope block but extracted zero string values -- regex likely stale",
    );
  }
  return values;
}

describe("KNOWN_VAULT_SCOPES stays synchronized with Python's PseudonymScope", () => {
  it("every known scope is a real PseudonymScope member", () => {
    const pythonValues = readPythonPseudonymScopeValues();

    for (const value of KNOWN_VAULT_SCOPES) {
      expect(pythonValues).toContain(value);
    }
  });

  it("deliberately excludes organization -- the explorer never returns that scope", () => {
    const pythonValues = readPythonPseudonymScopeValues();
    expect(pythonValues).toContain("organization");
    expect(KNOWN_VAULT_SCOPES).not.toContain("organization");
  });

  it("is exactly request, document, session", () => {
    expect([...KNOWN_VAULT_SCOPES].sort()).toEqual(["document", "request", "session"]);
  });
});
