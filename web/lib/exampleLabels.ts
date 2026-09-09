/**
 * Turns one prepared example into something a prospective advisor can
 * actually read (T21 / issue #29).
 *
 * `GET /examples` returns `title = sample_id` -- see
 * `application/examples.py`, where the comment is explicit that the corpus
 * schema carries no human-authored title. That is the right call on the API
 * side: the backend returns stable identifiers and the UI owns presentation
 * copy (issue #29: "no scientific identifiers should be translated
 * internally; only presentation copy changes"). But rendering it verbatim
 * put `hr_department_aggregation_001` in front of the reviewer, which fails
 * issue #29's own acceptance criterion that "a reviewer unfamiliar with the
 * project can understand the purpose without external documentation".
 *
 * So the label is derived here, from the example's `purpose`: a small,
 * semantically meaningful, stable set (five values across the whole frozen
 * HR corpus), mapped to pt-BR in `copy.ts` like every other user-facing
 * string. The raw `example_id` is not discarded -- it is returned
 * separately as `technicalId`, for the caller to show as an on-demand
 * technical detail rather than as the primary label. That is the same
 * progressive-disclosure rule `docs/advisor-demo.md` applies everywhere
 * else: plain language first, identifiers available underneath.
 *
 * Fail-safe on an unrecognized purpose: this module falls back to the raw
 * id and reports `known: false`. It never invents a friendly label for a
 * purpose it does not actually have copy for -- a wrong-but-confident label
 * on a disclosure demo is worse than an ugly-but-accurate one, and a
 * purpose added to the corpus later should be visible as unstyled rather
 * than silently mislabeled.
 */

import type { ExampleSummary } from "./contracts";
import { copy } from "./copy";

export interface ExampleDescriptor {
  /** What the reviewer reads. Plain pt-BR for a known purpose. */
  label: string;
  /** The raw corpus sample id, for display as a technical detail only. */
  technicalId: string;
  /** `false` when this module has no copy for the example's purpose. */
  known: boolean;
}

function purposeLabel(purpose: string): string | undefined {
  return (copy.examplePurposes as Record<string, string | undefined>)[purpose];
}

/**
 * Describe one example, given the full listing it belongs to.
 *
 * The listing is needed only to decide numbering: several examples share a
 * purpose (six are `team_summary` in the frozen HR corpus), so a bare
 * purpose label would render six identical options. Numbering follows the
 * order the API returned, which is the corpus's own stable file order.
 */
export function describeExample(
  example: ExampleSummary,
  listing: readonly ExampleSummary[],
): ExampleDescriptor {
  const technicalId = example.example_id;
  const label = purposeLabel(example.purpose);

  if (label === undefined) {
    return { label: technicalId, technicalId, known: false };
  }

  const sharingPurpose = listing.filter((item) => item.purpose === example.purpose);
  if (sharingPurpose.length <= 1) {
    return { label, technicalId, known: true };
  }

  const position = sharingPurpose.findIndex((item) => item.example_id === technicalId) + 1;
  return { label: `${label} ${position}`, technicalId, known: true };
}
