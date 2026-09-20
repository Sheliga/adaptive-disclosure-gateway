import { describe, expect, it } from "vitest";

import { copy } from "./copy";
import { en } from "./copy.en";
import { describeInspectionAction } from "./inspectionActions";

/**
 * T27 / issue #69. Mirrors `outcomes.test.ts`'s fail-closed posture: an
 * action this module does not recognize must never be presented as one of
 * the four known actions, and the four known actions plus "untouched" must
 * each have a genuinely distinct visible label -- a defect where two
 * actions accidentally shared copy (e.g. both mapped to "Alterado") would
 * make the inspector's legend/labels ambiguous, and this is the test that
 * would catch it.
 */
describe("describeInspectionAction -- known actions", () => {
  it.each([
    ["preserve", copy.inspectionActions.preserve.label],
    ["pseudonymize", copy.inspectionActions.pseudonymize.label],
    ["generalize", copy.inspectionActions.generalize.label],
    ["remove", copy.inspectionActions.remove.label],
  ] as const)("describes %s with known: true and its own label", (action, expectedLabel) => {
    const descriptor = describeInspectionAction(action);

    expect(descriptor.known).toBe(true);
    expect(descriptor.label).toBe(expectedLabel);
    expect(descriptor.explanation.length).toBeGreaterThan(0);
    expect(descriptor.glyph.length).toBeGreaterThan(0);
  });

  it("gives all four known actions distinct visible labels", () => {
    const labels = (["preserve", "pseudonymize", "generalize", "remove"] as const).map(
      (action) => describeInspectionAction(action).label,
    );
    expect(new Set(labels).size).toBe(labels.length);
  });

  it("describes null (untouched) distinctly from every known action", () => {
    const untouched = describeInspectionAction(null);
    const knownLabels = (["preserve", "pseudonymize", "generalize", "remove"] as const).map(
      (action) => describeInspectionAction(action).label,
    );

    expect(untouched.known).toBe(true);
    expect(untouched.label).toBe(copy.inspectionActions.untouched.label);
    expect(knownLabels).not.toContain(untouched.label);
  });
});

describe("describeInspectionAction -- fails closed on an unrecognized action", () => {
  it("never presents an unknown action as one of the four known ones", () => {
    const descriptor = describeInspectionAction("quantum_redact");

    expect(descriptor.known).toBe(false);
    expect(descriptor.label).toBe(copy.inspectionActions.unknown.label);
    const knownLabels = (["preserve", "pseudonymize", "generalize", "remove"] as const).map(
      (action) => describeInspectionAction(action).label,
    );
    expect(knownLabels).not.toContain(descriptor.label);
  });

  it("also fails closed for block_request/task_dependent -- real DisclosureAction members that never appear on a segment", () => {
    // These are real Python enum members (see contracts.ts's
    // KNOWN_INSPECTION_ACTIONS docstring) but never legitimate values of an
    // actual segment's action -- this module treats them the same as any
    // other unrecognized string, never specially.
    expect(describeInspectionAction("block_request").known).toBe(false);
    expect(describeInspectionAction("task_dependent").known).toBe(false);
  });
});

describe("describeInspectionAction -- locale support", () => {
  it("uses the English copy table when passed explicitly", () => {
    const descriptor = describeInspectionAction("remove", en);
    expect(descriptor.label).toBe(en.inspectionActions.remove.label);
    expect(descriptor.label).not.toBe(copy.inspectionActions.remove.label);
  });
});
