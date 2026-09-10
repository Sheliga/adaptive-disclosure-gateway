import { describe, expect, it } from "vitest";

import { copy } from "./copy";

/**
 * Regression pin for a real defect (PR #50, correction 1): the
 * `strategyVsTreatmentExplanation` copy once claimed `recommended` means
 * "let the policy decide automatically" (i.e. resolution happens
 * dynamically, based on the document/policy). That is false --
 * `application/contracts.py`'s `_STRATEGY_TO_TREATMENT` is a static dict:
 * every explicit `b0`-`b4` strategy maps to the treatment it names, and
 * `recommended` maps unconditionally (today) to `b4`. Nothing inspects the
 * document or the policy engine to choose a treatment.
 *
 * This does NOT assert the sentence verbatim -- that would be brittle
 * against harmless rewording. It asserts the two false claims stay absent
 * and the true claim ("recommended" currently resolves to B4) stays
 * present, so this specific defect cannot silently come back.
 */
describe("copy.technicalDetails.strategyVsTreatmentExplanation", () => {
  const explanation = copy.technicalDetails.strategyVsTreatmentExplanation;

  it("never claims the policy dynamically decides the strategy/treatment", () => {
    expect(explanation).not.toMatch(/pol[ií]tica\s+decid/i);
  });

  it("never claims resolution happens automatically at request time", () => {
    expect(explanation).not.toMatch(/automaticamente/i);
  });

  it("states that an explicit B0-B4 strategy is a legal request value, not just recommended", () => {
    expect(explanation.toLowerCase()).toContain("b0");
    expect(explanation).toMatch(/estrat[ée]gia\s+b0[\s\S]{0,10}b4\s+expl[ií]cita/i);
  });

  it("states that recommended currently resolves to B4", () => {
    expect(explanation).toMatch(/recommended["']?\s+resolve\w*\s+para\s+b4/i);
  });
});
