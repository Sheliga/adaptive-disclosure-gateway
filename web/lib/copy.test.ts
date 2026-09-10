import { describe, expect, it } from "vitest";

import { copy, ptBR, resolveCopy, type AppCopy } from "./copy";
import { enUS } from "./copy.en-US";

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
describe("copy.en-US.technicalDetails.strategyVsTreatmentExplanation", () => {
  const explanation = enUS.technicalDetails.strategyVsTreatmentExplanation;

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
  ["en-US", enUS],
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

describe("copy.ts -- pt-BR and en-US implement the same translatable structure", () => {
  it("both locales expose exactly the same set of key paths", () => {
    const ptPaths = collectKeyPaths(ptBR).sort();
    const enPaths = collectKeyPaths(enUS).sort();
    expect(enPaths).toEqual(ptPaths);
  });

  it("a locale missing a key actually fails this test (proves the test can fail)", () => {
    const mutated: Record<string, unknown> = JSON.parse(JSON.stringify(enUS));
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

  it("resolves en-US to the English table", () => {
    expect(resolveCopy("en-US")).toBe(enUS);
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
describe("copy.en-US.technicalDetails.timingExplanation", () => {
  const explanation = enUS.technicalDetails.timingExplanation;

  it("states this is an operational measure, not the scientific latency metric", () => {
    expect(explanation).toMatch(/operational/i);
    expect(explanation).toMatch(/not the scientific latency metric/i);
  });
});

/** Type-level parity check: this line only compiles if AppCopy structurally
 * matches both tables -- see `Widen<T>` in `copy.ts`. Kept as a value (not
 * just a type assertion) so it participates in the module the way any other
 * import does; there is nothing to assert about it at runtime beyond "this
 * file compiled".
 */
const _typeParityCheck: AppCopy[] = [ptBR, enUS];
void _typeParityCheck;
