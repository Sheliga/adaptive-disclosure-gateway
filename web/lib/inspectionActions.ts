/**
 * Maps one `InspectionSegment.action` (T27 / issue #69) to what a reviewer
 * reads in the transformation inspector: a plain-language label, a
 * one-sentence explanation, and a non-color glyph identifier.
 *
 * FAIL-CLOSED, the same posture `lib/outcomes.ts` documents for
 * `DisclosureOutcome`: an action this module does not recognize must never
 * be presented as one of the four known actions (`preserve`, `pseudonymize`,
 * `generalize`, `remove`) -- it degrades to `known: false` with its own
 * "not recognized" copy. `null` is a distinct, always-known case (the
 * segment was untouched), never conflated with "unrecognized".
 */

import { KNOWN_INSPECTION_ACTIONS, type InspectionAction, type KnownInspectionAction } from "./contracts";
import type { AppCopy } from "./copy";
import { copy as defaultCopy } from "./copy";

export interface InspectionActionDescriptor {
  /** Plain-language label, e.g. "Removido", "Generalizado". */
  label: string;
  /** One-sentence "why"/"what happened" explanation. */
  explanation: string;
  /** A non-color glyph/icon identifier -- never markup, never a color. */
  glyph: string;
  /** `false` when the API returned an action this module does not recognize. */
  known: boolean;
}

function isKnownInspectionAction(action: InspectionAction): action is KnownInspectionAction {
  return (KNOWN_INSPECTION_ACTIONS as readonly string[]).includes(action);
}

const ACTION_GLYPHS: Record<KnownInspectionAction, string> = {
  preserve: "check-shield",
  pseudonymize: "mask",
  generalize: "blur",
  remove: "trash",
};

function actionCopyFor(
  appCopy: AppCopy,
): Record<KnownInspectionAction, { label: string; explanation: string }> {
  return {
    preserve: appCopy.inspectionActions.preserve,
    pseudonymize: appCopy.inspectionActions.pseudonymize,
    generalize: appCopy.inspectionActions.generalize,
    remove: appCopy.inspectionActions.remove,
  };
}

/**
 * `appCopy` defaults to the pt-BR table so existing callers/tests keep
 * behaving unchanged; a component under `LocaleProvider` passes its
 * resolved `useCopy()` value explicitly, matching every other `lib/*.ts`
 * presentation-mapping module in this codebase.
 */
export function describeInspectionAction(
  action: InspectionAction | null,
  appCopy: AppCopy = defaultCopy,
): InspectionActionDescriptor {
  if (action === null) {
    return {
      label: appCopy.inspectionActions.untouched.label,
      explanation: appCopy.inspectionActions.untouched.explanation,
      glyph: "minus",
      known: true,
    };
  }

  if (!isKnownInspectionAction(action)) {
    return {
      label: appCopy.inspectionActions.unknown.label,
      explanation: appCopy.inspectionActions.unknown.explanation,
      glyph: "alert-triangle",
      known: false,
    };
  }

  const actionCopy = actionCopyFor(appCopy)[action];
  return {
    label: actionCopy.label,
    explanation: actionCopy.explanation,
    glyph: ACTION_GLYPHS[action],
    known: true,
  };
}
