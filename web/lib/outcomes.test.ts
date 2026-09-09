import { describe, expect, it } from "vitest";

import type { CategoryDisclosureSummary } from "./contracts";
import { describeCategoryOutcome } from "./outcomes";
import { copy } from "./copy";

function category(overrides: Partial<CategoryDisclosureSummary>): CategoryDisclosureSummary {
  return {
    category: "employee_name",
    outcome: "removed",
    action: "remove",
    crosses_trust_boundary: false,
    occurrence_count: 1,
    required_for_task: null,
    technical_reason: "detected by rule X",
    policy_version: null,
    policy_restricted: null,
    impossible_under_policy: null,
    ...overrides,
  };
}

describe("describeCategoryOutcome — known outcomes", () => {
  it("maps removed to a protected, local, known descriptor", () => {
    const descriptor = describeCategoryOutcome(
      category({ outcome: "removed", crosses_trust_boundary: false }),
    );
    expect(descriptor.known).toBe(true);
    expect(descriptor.label).toBe("Removido");
    expect(descriptor.tone).toBe("protected");
    expect(descriptor.boundaryLabel).toBe(copy.outcomes.protectedLocally.label);
    expect(descriptor.glyph).toBeTruthy();
    expect(descriptor.explanation.length).toBeGreaterThan(0);
  });

  it("maps pseudonymized crossing the boundary to a sent, known descriptor", () => {
    const descriptor = describeCategoryOutcome(
      category({ outcome: "pseudonymized", crosses_trust_boundary: true }),
    );
    expect(descriptor.known).toBe(true);
    expect(descriptor.label).toBe("Substituído por pseudônimo");
    expect(descriptor.tone).toBe("sent");
    expect(descriptor.boundaryLabel).toBe(copy.outcomes.sentToProvider.label);
  });

  it("maps generalized crossing the boundary to sent", () => {
    const descriptor = describeCategoryOutcome(
      category({ outcome: "generalized", crosses_trust_boundary: true }),
    );
    expect(descriptor.label).toBe("Generalizado");
    expect(descriptor.tone).toBe("sent");
  });

  it("maps preserved to the task-necessity label", () => {
    const descriptor = describeCategoryOutcome(
      category({ outcome: "preserved", crosses_trust_boundary: true, required_for_task: true }),
    );
    expect(descriptor.label).toBe("Mantido porque é necessário para a tarefa");
    expect(descriptor.tone).toBe("sent");
  });

  it("maps blocked to the blocked tone regardless of the boundary flag", () => {
    const blockedButFlagTrue = describeCategoryOutcome(
      category({ outcome: "blocked", crosses_trust_boundary: true }),
    );
    expect(blockedButFlagTrue.label).toBe("Bloqueado");
    expect(blockedButFlagTrue.tone).toBe("blocked");

    const blockedFlagFalse = describeCategoryOutcome(
      category({ outcome: "blocked", crosses_trust_boundary: false }),
    );
    expect(blockedFlagFalse.tone).toBe("blocked");
  });
});

describe("describeCategoryOutcome — fail-closed on unknown outcomes", () => {
  it("never renders an unrecognized outcome as known, protected, safe or local", () => {
    const descriptor = describeCategoryOutcome(
      category({ outcome: "quantum_redacted", crosses_trust_boundary: false }),
    );

    expect(descriptor.known).toBe(false);
    expect(descriptor.tone).toBe("unknown");
    expect(descriptor.tone).not.toBe("protected");
    expect(descriptor.label.toLowerCase()).not.toContain("protegido");
    expect(descriptor.boundaryLabel.toLowerCase()).not.toContain("protegido");
    expect(descriptor.boundaryLabel.toLowerCase()).not.toContain("local");
    // Must say the action could not be interpreted / needs review.
    expect(descriptor.label).toBe(copy.outcomes.unknown.label);
    expect(descriptor.explanation).toBe(copy.outcomes.unknown.explanation);
  });

  it("stays unknown/unsafe even when crosses_trust_boundary is false", () => {
    // The dangerous failure mode: an unrecognized code paired with a
    // boundary flag of `false` must NOT be interpreted as "stayed local
    // and therefore safe" -- it must still degrade to unknown.
    const descriptor = describeCategoryOutcome(
      category({ outcome: "future_action_v2", crosses_trust_boundary: false }),
    );
    expect(descriptor.known).toBe(false);
    expect(descriptor.tone).toBe("unknown");
  });
});

describe("describeCategoryOutcome — reads crosses_trust_boundary, never re-derives it", () => {
  it("follows the flag=true even for an outcome one would guess stays local", () => {
    // "removed" would naively suggest "never sent" -- but this module must
    // trust the flag the application layer already computed, not its own
    // guess from the outcome code.
    const descriptor = describeCategoryOutcome(
      category({ outcome: "removed", crosses_trust_boundary: true }),
    );
    expect(descriptor.tone).toBe("sent");
    expect(descriptor.boundaryLabel).toBe(copy.outcomes.sentToProvider.label);
    expect(descriptor.crossesTrustBoundary).toBe(true);
  });

  it("follows the flag=false even for an outcome one would guess is sent", () => {
    // "pseudonymized" would naively suggest "crosses the boundary" -- but
    // if the application layer says otherwise, this module must follow it.
    const descriptor = describeCategoryOutcome(
      category({ outcome: "pseudonymized", crosses_trust_boundary: false }),
    );
    expect(descriptor.tone).toBe("protected");
    expect(descriptor.boundaryLabel).toBe(copy.outcomes.protectedLocally.label);
    expect(descriptor.crossesTrustBoundary).toBe(false);
  });
});
