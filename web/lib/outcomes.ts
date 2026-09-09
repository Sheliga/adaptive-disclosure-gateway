/**
 * Maps one `CategoryDisclosureSummary` (from the API's disclosure summary --
 * see `lib/contracts.ts`) to what a novice reviewer sees: a plain-language
 * label, a one-sentence "why" explanation, a non-color glyph, and a
 * semantic tone.
 *
 * FAIL-CLOSED is the core property of this module (`docs/advisor-demo.md`,
 * CLAUDE.md's no-leak invariant read broadly): an `outcome` this module does
 * not recognize must never render as protected/safe/local. It degrades to
 * `known: false` with a review-me label -- never to any of the "safe"
 * tones. A future disclosure outcome added on the Python side therefore
 * degrades to "unknown -- verify" here automatically, without this module
 * changing, rather than silently falling through to a "protected" default.
 *
 * The local-vs-sent split is read from `category.crosses_trust_boundary`
 * ONLY. It is never re-derived by pattern-matching the outcome code --
 * that flag is exactly what the application layer already computed as the
 * authoritative trust-boundary fact (see `application/contracts.py`'s
 * `CategoryDisclosureSummary` docstring), and re-deriving it here would be
 * the "UI reimplements security semantics" mistake CLAUDE.md forbids.
 * `outcomes.test.ts` pins this with a summary whose flag deliberately
 * disagrees with what the outcome code alone would suggest.
 */

import type { CategoryDisclosureSummary, DisclosureOutcome, KnownDisclosureOutcome } from "./contracts";
import { KNOWN_DISCLOSURE_OUTCOMES } from "./contracts";
import { copy } from "./copy";

/**
 * Semantic tone token names. These correspond 1:1 to the CSS custom
 * properties defined in `app/globals.css` (`--tone-protected`,
 * `--tone-sent`, `--tone-blocked`, `--tone-unknown`) -- components consume
 * this string to pick a token, never a raw color.
 */
export type DisclosureTone = "protected" | "sent" | "blocked" | "unknown";

export interface OutcomeDescriptor {
  /** Plain-language action label, e.g. "Removido", "Generalizado". */
  label: string;
  /** One-sentence "why" explanation for the plain-language label. */
  explanation: string;
  /**
   * A non-color indicator name (a glyph/icon identifier, not markup and
   * not a color) -- issue #29's accessibility rule that color is never the
   * only indicator of a disclosure action or state. Components resolve
   * this to an actual icon/glyph; this module never renders one itself.
   */
  glyph: string;
  /** Semantic tone token name -- see `DisclosureTone`. */
  tone: DisclosureTone;
  /**
   * Whether this stayed local or crossed the trust boundary, phrased as
   * plain language ("Protegido localmente" / "Enviado ao modelo"). Derived
   * strictly from `crossesTrustBoundary`, independent of `label`/`tone`'s
   * blocked/unknown handling below.
   */
  boundaryLabel: string;
  /** `false` when the API returned an outcome this module does not recognize. */
  known: boolean;
  /** Passed through from the summary, for callers that need the raw flag too. */
  crossesTrustBoundary: boolean;
}

function isKnownOutcome(outcome: DisclosureOutcome): outcome is KnownDisclosureOutcome {
  return (KNOWN_DISCLOSURE_OUTCOMES as readonly string[]).includes(outcome);
}

const OUTCOME_GLYPHS: Record<KnownDisclosureOutcome, string> = {
  removed: "trash",
  pseudonymized: "mask",
  generalized: "blur",
  preserved: "check-shield",
  blocked: "block",
};

const OUTCOME_ACTION_COPY: Record<KnownDisclosureOutcome, { label: string; explanation: string }> = {
  removed: copy.outcomes.removed,
  pseudonymized: copy.outcomes.pseudonymized,
  generalized: copy.outcomes.generalized,
  preserved: copy.outcomes.preserved,
  blocked: copy.outcomes.blocked,
};

/**
 * Derives the tone for a KNOWN outcome strictly from
 * `crosses_trust_boundary` plus the single explicit `blocked` special case
 * (a blocked request never sends anything, so it is neither "protected"
 * success nor "sent" -- it is its own tone). The unknown case is handled
 * separately by the caller, which never calls this at all -- an
 * unrecognized outcome must never be asserted safe/local just because the
 * flag happens to read `false`.
 */
function toneForKnownOutcome(
  outcome: KnownDisclosureOutcome,
  crossesTrustBoundary: boolean,
): Exclude<DisclosureTone, "unknown"> {
  if (outcome === "blocked") {
    return "blocked";
  }
  return crossesTrustBoundary ? "sent" : "protected";
}

function boundaryLabelFor(tone: DisclosureTone): string {
  switch (tone) {
    case "protected":
      return copy.outcomes.protectedLocally.label;
    case "sent":
      return copy.outcomes.sentToProvider.label;
    case "blocked":
      return copy.outcomes.blocked.label;
    case "unknown":
      return copy.outcomes.unknown.boundaryLabel;
  }
}

/**
 * The single entry point this module exists to provide: given one
 * category's disclosure summary, return everything a "what happens to my
 * data" row needs to render -- fail-closed for anything unrecognized.
 */
export function describeCategoryOutcome(category: CategoryDisclosureSummary): OutcomeDescriptor {
  const { outcome, crosses_trust_boundary: crossesTrustBoundary } = category;

  if (!isKnownOutcome(outcome)) {
    const tone: DisclosureTone = "unknown";
    return {
      label: copy.outcomes.unknown.label,
      explanation: copy.outcomes.unknown.explanation,
      glyph: "alert-triangle",
      tone,
      boundaryLabel: boundaryLabelFor(tone),
      known: false,
      crossesTrustBoundary,
    };
  }

  const tone = toneForKnownOutcome(outcome, crossesTrustBoundary);
  const actionCopy = OUTCOME_ACTION_COPY[outcome];
  return {
    label: actionCopy.label,
    explanation: actionCopy.explanation,
    glyph: OUTCOME_GLYPHS[outcome],
    tone,
    boundaryLabel: boundaryLabelFor(tone),
    known: true,
    crossesTrustBoundary,
  };
}
