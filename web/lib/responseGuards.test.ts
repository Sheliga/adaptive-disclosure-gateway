import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { describe, expect, it } from "vitest";

/**
 * The drift test for `lib/responseGuards.ts`.
 *
 * `lib/api.test.ts` proves the guards reject the bodies they are supposed
 * to reject. It cannot prove they are COMPLETE -- a field added to
 * `contracts.ts` later and never checked would leave every one of those
 * tests green while the UI silently reads an unvalidated value again. That
 * is the exact failure the hand-written-guard approach risks, so it is
 * pinned here instead of being left to review.
 *
 * The check reads `contracts.ts` as text (not via import: interfaces are
 * erased at runtime, so there is nothing to reflect over) and asserts that
 * every field of every interface reachable from a validated response is
 * named in `responseGuards.ts`. Adding a field to the contract without
 * guarding it fails this test.
 */

const here = path.dirname(fileURLToPath(import.meta.url));

function readLibSource(basename: string): string {
  return readFileSync(path.resolve(here, basename), "utf-8");
}

/**
 * The interfaces that make up the four response bodies this app decodes,
 * including the nested ones. Listed explicitly rather than crawled: the
 * list is short, and a wrong crawl would silently shrink the assertion.
 */
const VALIDATED_CONTRACT_INTERFACES = [
  // GET /health
  "HealthResponse",
  "ProviderHealth",
  // GET /examples
  "ExamplesResponse",
  "ExampleSummary",
  "DocumentTypesResponse",
  "DocumentType",
  // POST /disclosure/preview
  "PreviewResponse",
  "DocumentPreviewResponse",
  "DisclosureSummary",
  "CategoryDisclosureSummary",
  "SafeGovernanceView",
  "ProviderMode",
  // T27 / issue #69 -- PreviewResponse.inspection
  "DisclosureInspection",
  "InspectionSegment",
  // POST /disclosure/execute
  "ExecuteResponse",
  "ProviderStage",
  "ReconstructionStage",
  // POST /disclosure/compare
  "CompareResponse",
  "StrategyComparisonEntry",
  // POST /documents/export / POST /documents/restore (T26/#67, T28/#70)
  "ExportResponse",
  "RestoreResponse",
  // GET /api/demo/features (web-only)
  "DemoFeaturesResponse",
] as const;

/** The top-level response bodies that carry a `contract_version`. */
const TOP_LEVEL_RESPONSE_GUARDS = [
  "isHealthResponse",
  "isExamplesResponse",
  "isDocumentTypesResponse",
  "isPreviewResponse",
  "isDocumentPreviewResponse",
  "isExecuteResponse",
  "isCompareResponse",
  "isExportResponse",
  "isRestoreResponse",
] as const;

function declaredFieldsOf(source: string, interfaceName: string): string[] {
  const match = source.match(
    new RegExp(`export interface ${interfaceName}(?: extends [^{]+)? \\{([\\s\\S]*?)\\n\\}`),
  );
  if (!match) {
    throw new Error(
      `could not locate \`export interface ${interfaceName}\` in contracts.ts -- ` +
        "has it been renamed, removed, or reformatted?",
    );
  }

  const fields = [...match[1].matchAll(/^\s{2}([a-z_][a-z0-9_]*)\??:/gm)].map(
    (fieldMatch) => fieldMatch[1],
  );
  if (fields.length === 0) {
    throw new Error(
      `found interface ${interfaceName} but extracted zero fields -- regex likely stale`,
    );
  }
  return fields;
}

describe("responseGuards covers every field of every validated response contract", () => {
  it("names each declared field in a runtime check", () => {
    const contracts = readLibSource("contracts.ts");
    const guards = readLibSource("responseGuards.ts");

    for (const interfaceName of VALIDATED_CONTRACT_INTERFACES) {
      for (const field of declaredFieldsOf(contracts, interfaceName)) {
        if (field === "contract_version") {
          // Checked once, centrally, by `declaresKnownContractVersion` --
          // asserted separately below.
          continue;
        }
        expect(
          guards.includes(`value.${field}`),
          `${interfaceName}.${field} is declared in contracts.ts but never checked in responseGuards.ts`,
        ).toBe(true);
      }
    }
  });

  it("gates every top-level response on the contract version", () => {
    const guards = readLibSource("responseGuards.ts");

    for (const guardName of TOP_LEVEL_RESPONSE_GUARDS) {
      const body = guards.match(
        new RegExp(`export const ${guardName}[\\s\\S]*?;\\n`),
      );
      expect(body, `${guardName} not found in responseGuards.ts`).not.toBeNull();
      expect(
        (body as RegExpMatchArray)[0].includes("declaresKnownContractVersion(value)"),
        `${guardName} does not assert the contract version it was written against`,
      ).toBe(true);
    }
  });

  it("never widens a boolean check into a truthiness check", () => {
    // The whole defect this module exists for is `undefined`/`"false"`
    // passing a truthiness test. `isBoolean` is the only thing standing
    // between the two, so it must stay a `typeof` check.
    const guards = readLibSource("responseGuards.ts");

    expect(guards).toContain('return typeof value === "boolean";');
    expect(guards).toContain("isBoolean(value.crosses_trust_boundary)");
    expect(guards).toContain("isBoolean(value.failed)");
    // `unsafe_control_baseline` is what the comparison screen's B0 warning
    // is derived from -- a truthiness check here would let the string
    // "false" flip the warning on and an absent field silence it.
    expect(guards).toContain("isBoolean(value.unsafe_control_baseline)");
  });
});

/**
 * T27/T28 (issues #69-#70) field-set drift test: reads
 * `application/wire.py`'s own pydantic model field declarations off disk
 * (the actual wire shape, not `application/contracts.py`'s domain shape) and
 * asserts the TS interfaces this module validates declare exactly the same
 * field NAMES -- not types, which a text scrape cannot check meaningfully,
 * but names, which is exactly the thing a hand-maintained mirror can forget
 * to update when a field is added, renamed or removed on the Python side.
 * `contracts.test.ts` already does the analogous thing for the domain-level
 * enums/order these guards read; this is the same technique applied to the
 * wire-level model shapes those guards validate field-by-field.
 */
describe("T27/T28 wire field sets stay synchronized with application/wire.py", () => {
  function readWireSource(): string {
    const here = path.dirname(fileURLToPath(import.meta.url));
    const wirePath = path.resolve(
      here,
      "..",
      "..",
      "src",
      "adaptive_disclosure_gateway",
      "application",
      "wire.py",
    );
    return readFileSync(wirePath, "utf-8");
  }

  function readPythonModelFields(source: string, className: string): string[] {
    const classMatch = source.match(
      new RegExp(`class ${className}\\(BaseModel\\):[\\s\\S]*?(?=\\nclass |$)`),
    );
    if (!classMatch) {
      throw new Error(
        `could not locate \`class ${className}(BaseModel):\` in application/wire.py -- ` +
          "has it been renamed, removed, or moved?",
      );
    }
    const fields = [...classMatch[0].matchAll(/^ {4}([a-z_][a-z0-9_]*): /gm)].map(
      (match) => match[1],
    );
    if (fields.length === 0) {
      throw new Error(`found class ${className} but extracted zero fields -- regex likely stale`);
    }
    return fields;
  }

  function readTsInterfaceFields(interfaceName: string): string[] {
    const contracts = readLibSource("contracts.ts");
    return declaredFieldsOf(contracts, interfaceName);
  }

  it.each([
    ["InspectionSegmentModel", "InspectionSegment"],
    ["DisclosureInspectionModel", "DisclosureInspection"],
    ["ExportResponse", "ExportResponse"],
    ["RestoreResponse", "RestoreResponse"],
  ])("%s (Python) and %s (TS) declare the exact same field set", (pythonClass, tsInterface) => {
    const pythonFields = readPythonModelFields(readWireSource(), pythonClass);
    const tsFields = readTsInterfaceFields(tsInterface);

    expect([...tsFields].sort()).toEqual([...pythonFields].sort());
  });
});
