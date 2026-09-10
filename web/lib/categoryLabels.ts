/**
 * Turns one sensitive-data category identifier into what a novice reviewer
 * reads (T21 / issue #29).
 *
 * The API reports each detected category by its frozen policy identifier --
 * `employee_name`, `cpf`, `salary`, `department`, `medical_data` (see
 * `configs/policies/hr-v1|v2|v3.yaml`). That is correct on the API side and
 * nothing here changes it: the identifier stays verbatim in the contract,
 * in `lib/outcomes.ts`, in the React keys, and in anything the UI ever
 * sends back. This module only decides what the reviewer SEES.
 *
 * It exists because the review screen is a consent screen. A row headlined
 * `medical_data` asks someone to approve a disclosure using the vocabulary
 * of the experiment rather than the vocabulary of their own document --
 * which is exactly the acceptance criterion issue #29 states for T21 ("a
 * reviewer unfamiliar with the project can understand ... without external
 * documentation"). `lib/exampleLabels.ts` already made this call for
 * example ids; this is the same rule applied to the other identifier the
 * primary flow puts in front of the user.
 *
 * FAIL-CLOSED PRESENTATION, and the direction matters. The obvious fallback
 * for an unmapped identifier is to prettify it -- title-case it, swap
 * underscores for spaces -- and that is the one thing this module must not
 * do. `party_name` would render as "Party name": confident, plausible, and
 * never reviewed by anyone. On a screen whose purpose is informed consent
 * about sensitive data, a wrong-but-authoritative label is worse than an
 * honest "not recognized". So an unmapped category is reported as
 * `known: false` with the explicit unrecognized copy, and its raw
 * identifier is handed back separately for the caller to show as a
 * technical detail -- the reviewer can then report precisely what the API
 * sent. This mirrors `lib/outcomes.ts`'s posture for an unrecognized
 * `outcome`, and the two compose: an unknown category with an unknown
 * outcome degrades on both axes instead of either one guessing.
 */

import type { AppCopy } from "./copy";
import { copy as defaultCopy } from "./copy";

export interface CategoryDescriptor {
  /** What the reviewer reads, in the caller's locale. */
  label: string;
  /** The raw policy identifier, for display as a technical detail only. */
  technicalId: string;
  /** `false` when this module has no reviewed copy for the identifier. */
  known: boolean;
}

/**
 * `Object.hasOwn` rather than `labels[identifier]`: the copy table is a
 * plain object literal, so a bare index lookup of `"constructor"` or
 * `"toString"` walks the prototype chain and returns a function, which
 * `typeof x === "string"` would reject but only by accident. Asking about
 * own keys says what is actually meant -- an API-supplied string is never
 * allowed to reach into anything this table did not declare.
 */
function labelFor(identifier: string, appCopy: AppCopy): string | undefined {
  const labels: Record<string, string> = appCopy.categories.labels;
  return Object.hasOwn(labels, identifier) ? labels[identifier] : undefined;
}

/**
 * Describe one category identifier as received from the API, verbatim.
 *
 * `appCopy` defaults to the pt-BR table so existing callers/tests keep
 * behaving unchanged; a component under `LocaleProvider` passes its
 * resolved `useCopy()` value explicitly (T21 fourth slice / #29).
 */
export function describeCategory(identifier: string, appCopy: AppCopy = defaultCopy): CategoryDescriptor {
  const label = labelFor(identifier, appCopy);

  if (label === undefined) {
    return {
      label: appCopy.categories.unrecognized,
      technicalId: identifier,
      known: false,
    };
  }

  return { label, technicalId: identifier, known: true };
}
