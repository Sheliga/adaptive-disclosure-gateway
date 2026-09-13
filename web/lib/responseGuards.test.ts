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
  // POST /disclosure/execute
  "ExecuteResponse",
  "ProviderStage",
  "ReconstructionStage",
  // POST /disclosure/compare
  "CompareResponse",
  "StrategyComparisonEntry",
] as const;

/** The five top-level response bodies, each of which carries a version. */
const TOP_LEVEL_RESPONSE_GUARDS = [
  "isHealthResponse",
  "isExamplesResponse",
  "isDocumentTypesResponse",
  "isPreviewResponse",
  "isDocumentPreviewResponse",
  "isExecuteResponse",
  "isCompareResponse",
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
