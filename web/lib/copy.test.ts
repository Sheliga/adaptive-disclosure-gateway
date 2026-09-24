import { describe, expect, it } from "vitest";

import { copy, ptBR, resolveCopy, type AppCopy } from "./copy";
import { en } from "./copy.en";

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

/**
 * Same pins as above, extended to English (T21 fourth slice / #29). The
 * English copy is a fresh, natural-English rendering, not a word-for-word
 * translation -- so these assert the same TRUE/FALSE claims the pt-BR pins
 * assert, using English-shaped patterns, never the pt-BR sentence itself.
 */
describe("copy.en.technicalDetails.strategyVsTreatmentExplanation", () => {
  const explanation = en.technicalDetails.strategyVsTreatmentExplanation;

  it("never claims the policy dynamically chooses/decides/selects the strategy", () => {
    expect(explanation).not.toMatch(/polic(y|ies)\s+.*(choose|decide|select)/i);
  });

  it("never claims resolution happens automatically at request time", () => {
    expect(explanation).not.toMatch(/automatically/i);
  });

  it("states that an explicit B0-B4 strategy is a legal request value, not just recommended", () => {
    expect(explanation.toLowerCase()).toContain("b0");
    expect(explanation).toMatch(/explicit\s+b0[\s\S]{0,10}b4\s+strategy/i);
  });

  it("states that recommended currently resolves to B4", () => {
    expect(explanation).toMatch(/recommended["']?\s+resolves?\s+to\s+b4/i);
  });
});

/**
 * Structural guard against the evaluative-adjective drift CLAUDE.md warns
 * about specifically for English copy: B0 must never read as "bad"/"wrong"/
 * an "insecure strategy"/"worst", and B4 must never read as "best"/"most
 * secure"/"scientifically superior" -- in EITHER locale, not just the one
 * that happened to prompt the rule. Scans every string leaf reachable from
 * the locale object, not just the fields already covered above, so a
 * regression anywhere in the copy tree (a new field, a reworded caption)
 * cannot slip past a check aimed at only one known field.
 */
function flattenStrings(value: unknown, out: string[] = []): string[] {
  if (typeof value === "string") {
    out.push(value);
  } else if (Array.isArray(value)) {
    for (const item of value) {
      flattenStrings(item, out);
    }
  } else if (value !== null && typeof value === "object") {
    for (const item of Object.values(value as Record<string, unknown>)) {
      flattenStrings(item, out);
    }
  }
  return out;
}

const FORBIDDEN_RANKING_LANGUAGE = [
  /\bbest strategy\b/i,
  /\bwinner\b/i,
  /\bmost secure\b/i,
  /\bscientifically superior\b/i,
  /\bmelhor estrat[ée]gia\b/i,
  /\bvencedor(a)?\b/i,
  /\bmais segura\b/i,
  /\bcientificamente superior\b/i,
];

/**
 * CLAUDE.md names these specific evaluative adjectives for B0 by name: never
 * "bad", "wrong", "insecure strategy", "worst". Checked narrowly (as whole
 * words / the exact phrase) rather than broadly, since "insecure" alone
 * would be legitimate prose describing WHY B0 has no protection -- the rule
 * is against evaluative labeling of the treatment itself, not against
 * describing what it does.
 */
const FORBIDDEN_B0_EVALUATIVE_LANGUAGE = [/\bbad\b/i, /\bwrong\b/i, /\binsecure strategy\b/i, /\bworst\b/i];

describe.each([
  ["pt-BR", ptBR],
  ["en", en],
] as const)("copy.%s -- never renders B0 as bad/wrong/insecure/worst or B4 as best/winner", (_locale, table) => {
  const strings = flattenStrings(table);
  const treatmentStrings = flattenStrings((table as { treatments?: unknown }).treatments ?? {});

  it("contains no ranking/superiority language anywhere in the locale table", () => {
    for (const pattern of FORBIDDEN_RANKING_LANGUAGE) {
      for (const text of strings) {
        expect(text).not.toMatch(pattern);
      }
    }
  });

  it("never describes B0/B4 treatment copy with evaluative bad/worst language", () => {
    for (const pattern of FORBIDDEN_B0_EVALUATIVE_LANGUAGE) {
      for (const text of treatmentStrings) {
        expect(text).not.toMatch(pattern);
      }
    }
  });
});

/**
 * Key-parity backstop (CLAUDE.md/TDD: a real, not merely sanity, check). The
 * primary enforcement is `AppCopy`'s structural type (see `copy.ts`'s
 * `Widen<T>`) rejecting a missing/extra/wrong-shaped key at COMPILE time --
 * this test instead catches a defect a type system cannot: two modules that
 * both compile against `AppCopy` but were hand-edited so their actual
 * exported VALUES have drifted (e.g. someone widens the type by hand-casting
 * `as AppCopy` somewhere, silently reintroducing a runtime gap). It fails
 * from a real defect: delete a key from one locale object at runtime (via a
 * mutated clone) and this test catches it even though nothing else would.
 */
function collectKeyPaths(value: unknown, prefix = "", out: string[] = []): string[] {
  if (Array.isArray(value)) {
    // Arrays are compared by shape/length-independence (Widen widens a
    // tuple to a general array) -- inspect only the first element's shape,
    // if any, since count is allowed to differ between locales.
    if (value.length > 0) {
      collectKeyPaths(value[0], `${prefix}[]`, out);
    }
    return out;
  }
  if (value !== null && typeof value === "object") {
    for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
      collectKeyPaths(item, prefix ? `${prefix}.${key}` : key, out);
    }
    return out;
  }
  out.push(prefix);
  return out;
}

describe("copy.ts -- pt-BR and en implement the same translatable structure", () => {
  it("both locales expose exactly the same set of key paths", () => {
    const ptPaths = collectKeyPaths(ptBR).sort();
    const enPaths = collectKeyPaths(en).sort();
    expect(enPaths).toEqual(ptPaths);
  });

  it("a locale missing a key actually fails this test (proves the test can fail)", () => {
    const mutated: Record<string, unknown> = JSON.parse(JSON.stringify(en));
    delete mutated.buttons;
    const ptPaths = collectKeyPaths(ptBR).sort();
    const mutatedPaths = collectKeyPaths(mutated).sort();
    expect(mutatedPaths).not.toEqual(ptPaths);
  });
});

describe("resolveCopy", () => {
  it("resolves pt-BR to the pt-BR table", () => {
    expect(resolveCopy("pt-BR")).toBe(ptBR);
  });

  it("resolves en to the English table", () => {
    expect(resolveCopy("en")).toBe(en);
  });

  it("the default export -- copy -- is the pt-BR table", () => {
    expect(copy).toBe(ptBR);
  });
});

/**
 * `total_ms` framing must survive translation exactly as strictly as the
 * strategy/treatment framing above -- CLAUDE.md calls it out by name as the
 * scientific claim most likely to drift in English.
 */
describe("copy.en.technicalDetails.timingExplanation", () => {
  const explanation = en.technicalDetails.timingExplanation;

  it("states this is an operational measure, not the scientific latency metric", () => {
    expect(explanation).toMatch(/operational/i);
    expect(explanation).toMatch(/not the scientific latency metric/i);
  });
});

/**
 * PR #83 review follow-up (Finding 2): the welcome screen's
 * `howItWorks.transformations` before/after examples must match the REAL
 * output shapes the pipeline produces, not an invented placeholder --
 * `src/adaptive_disclosure_gateway/transformations/generalization.py`'s
 * `NumericBandStrategy.generalize` returns `f"{prefix}{int(lower)}-{int(upper)}"`
 * (e.g. `"R$ 125000-130000"`, never a "Between X and Y" sentence);
 * `decision_application.py`'s `_allowed_result` (shared by every treatment
 * beyond B1) sets `transformed = None` for `DisclosureAction.REMOVE`, which
 * is joined into the payload as `""` -- there is no `[REDACTED:...]` or
 * `[removido]` placeholder anywhere in the pipeline, the value is simply
 * gone; and `vault/in_memory.py`'s `_make_pseudonym` mints
 * `f"PSEUDO-{category}-{token}"` with a 32-hex-character CSPRNG token, never
 * an `EMPLOYEE_XXXX`/`FUNCIONARIO_XXXX`-shaped string. This pins the real
 * shapes so a future edit cannot silently reintroduce the old, fabricated
 * examples.
 */
describe.each([
  ["pt-BR", ptBR],
  ["en", en],
] as const)("copy.%s.howItWorks.transformations -- examples match real pipeline output shapes", (_locale, table) => {
  const { remove, pseudonymize, generalize } = table.howItWorks.transformations;

  it("REMOVE's 'after' has no bracketed placeholder -- the value is simply gone", () => {
    expect(remove.after).not.toMatch(/\[.*\]/);
  });

  it("PSEUDONYMIZE's 'after' matches the real PSEUDO-{category}-{32 hex chars} vault token shape", () => {
    expect(pseudonymize.after).toMatch(/^PSEUDO-[a-z_]+-[0-9a-f]{32}$/);
  });

  it("GENERALIZE's 'after' matches the real NumericBandStrategy '{prefix}{int}-{int}' band shape", () => {
    expect(generalize.after).toMatch(/^R\$ \d+-\d+$/);
  });
});

/**
 * #103 review fix (PR #108): `beforeAfter`/`resultRecap` (the primary
 * before/after used in Review, the read-only Approved Review, and the
 * Result recap) once claimed the disclosed side is byte-identical to what
 * LATER crosses the boundary at execute time ("Exatamente esta
 * representação cruza a fronteira ... quando você confirmar" / "Exactly
 * this representation crosses the boundary ... when you confirm"). That is
 * only structurally guaranteed for upload (confirmation-token-bound
 * `execute_document`); for paste/example, `executeDisclosure` independently
 * recomputes the decision at execute time with no binding to the previewed
 * decision, so the earlier wording overclaimed for two of the three entry
 * modes. No string in either block, in either locale, may reassert that
 * identity.
 */
describe.each([
  ["pt-BR", ptBR],
  ["en", en],
] as const)("copy.%s.beforeAfter/resultRecap -- no preview-execute identity claim", (_locale, table) => {
  const allStrings = [...Object.values(table.beforeAfter), ...Object.values(table.resultRecap)].filter(
    (value): value is string => typeof value === "string",
  );

  it("contains no 'exactly'/'exatamente' claim", () => {
    for (const value of allStrings) {
      expect(value).not.toMatch(/exatamente|exactly/i);
    }
  });

  it("the Review disclosed caption reads as prepared-for-review, not as a send guarantee", () => {
    const caption = table.beforeAfter.disclosedCaptionReview;
    expect(caption).toMatch(/prepar|revis/i);
  });
});

/**
 * Round-2 #103 review fix (PR #108): three remaining overclaims survived the
 * first round. All three are checked here at the copy level (see the
 * matching component-level tests in `DisclosureTransformationSummary.test.tsx`
 * and `ResultScreen.test.tsx` for the rendered-DOM side of the same fixes).
 */
describe.each([
  ["pt-BR", ptBR],
  ["en", en],
] as const)("copy.%s -- round-2 #103 review fixes (PR #108)", (_locale, table) => {
  /**
   * Fix 1: the Review "what crosses the boundary" heading and its
   * payload-disclosure toggle once read "O que será enviado ao LLM externo"
   * / "Ver o payload exato que seria enviado" ("What will be sent" / "View
   * the exact payload that would be sent") -- both promise a future-send
   * identity the preview does not structurally guarantee for paste/example
   * (only upload's `execute_document` is confirmation-token-bound to the
   * previewed decision; paste/example independently recompute it). Neither
   * string may reassert that promise, in either its "será enviado"/"will be
   * sent" phrasing or an "exato"/"exact" claim about the payload.
   */
  it("review.willBeSentHeading and review.showPayloadToggle carry no exact/future-send claim", () => {
    for (const value of [table.review.willBeSentHeading, table.review.showPayloadToggle]) {
      expect(value).not.toMatch(/exat|exact|ser[áa]\s+enviado|will be sent/i);
    }
  });

  /**
   * Fix 2: `resultRecap.sent` once unconditionally called `final_answer`
   * "a resposta reconstruída localmente" / "the answer reconstructed
   * locally". `final_answer` may be the provider's response completely
   * unchanged (see `ReconstructionStage`); only `buildReconstructionNote` in
   * `ResultScreen.tsx` may make a reconstruction claim, and only when
   * `reconstruction.attempted && changed_from_provider_response === true`.
   * No string in `resultRecap` (any of the three provider-state variants)
   * may claim a reconstruction happened.
   */
  it("resultRecap never claims a reconstruction -- that claim belongs only to result.reconstructionApplied", () => {
    for (const value of Object.values(table.resultRecap)) {
      if (typeof value === "string") {
        expect(value).not.toMatch(/reconstru|restaur|restored/i);
      }
    }
  });

  /**
   * Fix 3: `beforeAfter.originalCaption` once said "Ele não sai daqui." /
   * "It does not leave." -- an absolute claim that does not hold for a
   * PRESERVE segment (kept, sent unchanged) or a no-change request (nothing
   * transformed, the same content crosses the boundary). No string in
   * `beforeAfter` may assert the original never leaves, and the caption
   * must still positively identify which side is the original.
   */
  it("no beforeAfter string claims the original never leaves the gateway", () => {
    for (const value of Object.values(table.beforeAfter)) {
      if (typeof value === "string") {
        expect(value).not.toMatch(/n[ãa]o sai|does not leave|never leaves|nunca sai/i);
      }
    }
  });

  it("originalCaption still positively identifies the original side", () => {
    expect(table.beforeAfter.originalCaption.toLowerCase()).toContain("original");
  });
});

/** Type-level parity check: this line only compiles if AppCopy structurally
 * matches both tables -- see `Widen<T>` in `copy.ts`. Kept as a value (not
 * just a type assertion) so it participates in the module the way any other
 * import does; there is nothing to assert about it at runtime beyond "this
 * file compiled".
 */
const _typeParityCheck: AppCopy[] = [ptBR, en];
void _typeParityCheck;
