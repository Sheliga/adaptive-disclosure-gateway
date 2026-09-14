/**
 * T29 / issue #72 -- turns one `VaultExplorerResponse.scope` identifier into
 * what the local operator reads, on the demo vault explorer panel.
 *
 * Same split, and the same reason, as `lib/categoryLabels.ts`'s
 * `describeCategory`: the API reports each scope by its frozen
 * `PseudonymScope` identifier (`request`, `document`, `session` -- see
 * `lib/contracts.ts`'s `KNOWN_VAULT_SCOPES`), and that identifier stays
 * verbatim everywhere it travels (the contract, the React key). This
 * module only decides what a human READS for it.
 *
 * FAIL-CLOSED PRESENTATION, same posture as `describeCategory`: an
 * unmapped scope is reported as `known: false` with the explicit
 * unrecognized copy, never prettified from its identifier -- a confident
 * but wrong label about what a reversible mapping's scope actually is
 * would be worse than an honest "not recognized" on a screen whose whole
 * purpose is showing the local operator exactly what stayed local.
 */

import type { AppCopy } from "./copy";
import { copy as defaultCopy } from "./copy";

export interface VaultScopeDescriptor {
  /** What the operator reads, in the caller's locale. */
  label: string;
  /** A short explanation of what this scope means for reversibility. */
  explanation: string | null;
  /** The raw scope identifier, for display as a technical detail only. */
  technicalId: string;
  /** `false` when this module has no reviewed copy for the identifier. */
  known: boolean;
}

/**
 * `Object.hasOwn` rather than a bare index lookup -- see
 * `lib/categoryLabels.ts`'s `labelFor` for why a plain `labels[identifier]`
 * on an API-supplied string is unsafe.
 */
function labelFor(identifier: string, appCopy: AppCopy): string | undefined {
  const labels: Record<string, string> = appCopy.vaultScopes.labels;
  return Object.hasOwn(labels, identifier) ? labels[identifier] : undefined;
}

function explanationFor(identifier: string, appCopy: AppCopy): string | undefined {
  const explanations: Record<string, string> = appCopy.vaultScopes.explanations;
  return Object.hasOwn(explanations, identifier) ? explanations[identifier] : undefined;
}

/**
 * Describe one `scope` identifier as received from the API, verbatim.
 *
 * `appCopy` defaults to the pt-BR table so existing callers/tests keep
 * behaving unchanged; a component under `LocaleProvider` passes its
 * resolved `useCopy()` value explicitly, same convention as
 * `describeCategory`.
 */
export function describeVaultScope(
  identifier: string,
  appCopy: AppCopy = defaultCopy,
): VaultScopeDescriptor {
  const label = labelFor(identifier, appCopy);

  if (label === undefined) {
    return {
      label: appCopy.vaultScopes.unrecognized,
      explanation: null,
      technicalId: identifier,
      known: false,
    };
  }

  return {
    label,
    explanation: explanationFor(identifier, appCopy) ?? null,
    technicalId: identifier,
    known: true,
  };
}
