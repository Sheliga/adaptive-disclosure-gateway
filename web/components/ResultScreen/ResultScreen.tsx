/**
 * Screen 4 -- "Resultado" (`docs/advisor-demo.md`, reorganized by T30 /
 * issue #82). The primary output is the final reconstructed answer,
 * followed immediately by a short, data-derived protections summary.
 * Everything else is progressively disclosed below that:
 *
 *  - Level 2: an "Entender o que aconteceu" disclosure (collapsed by
 *    default) holding the `Local -> Provedor externo -> Local` recap, and
 *    a "Comparar estratégias experimentais (B0–B4)" section framing
 *    `onCompareStrategies` explicitly as a research surface;
 *  - Level 3: a "Detalhes técnicos e ferramentas de pesquisa" section
 *    framing `onViewTechnicalDetails` and `VaultExplorerPanel` as the
 *    technical/audit layer.
 *
 * The research and technical sections keep their entry points as directly
 * clickable buttons (not gated behind an extra disclosure toggle) --
 * `docs/advisor-demo.md`'s "optionally discover" success criterion and this
 * screen's own pre-existing contract ("always available, on every
 * outcome") are satisfied by clear visual/heading framing ("secondary"),
 * not by hiding navigation. `VaultExplorerPanel` keeps its OWN internal
 * collapse (no fetch until its own toggle is opened) exactly as before.
 *
 * Two failure modes are handled as recorded outcomes, not crashes or
 * fabricated answers (issue #29):
 *  - a blocked execution (`execute.summary.status === "blocked"`);
 *  - a failed provider call (`execute.provider.failed`), which shows
 *    `failure_kind` (a safe category, never raw provider/error text) and
 *    never renders `final_answer` as if it were a real completion.
 *
 * The provider-mode notice comes from `describeProviderMode`
 * (`lib/providerMode.ts`), which this screen renders without interpreting
 * (issue #29: FakeProvider must be clearly labeled as a deterministic
 * demonstration provider, not a real model). The `health` prop is a
 * three-state value rather than `HealthResponse | null` precisely so a
 * FAILED health check is distinguishable here from one still in flight --
 * conflating them made a failed check silently erase the indication. Its
 * CSS is deliberately small/muted (T30) so it never outcompetes the answer.
 */

import { useState } from "react";

import { useCopy } from "@/i18n/useLocale";
import { describeCategory } from "@/lib/categoryLabels";
import type { AppCopy } from "@/lib/copy";
import type { DisplayError } from "@/lib/api";
import { KNOWN_DISCLOSURE_OUTCOMES } from "@/lib/contracts";
import type {
  CategoryDisclosureSummary,
  ExecuteResponse,
  KnownDisclosureOutcome,
  ReconstructionStage,
} from "@/lib/contracts";
import { describeCategoryOutcome } from "@/lib/outcomes";
import { describeProviderMode, type ProviderModeState } from "@/lib/providerMode";

import { VaultExplorerPanel } from "../VaultExplorerPanel/VaultExplorerPanel";
import styles from "./ResultScreen.module.css";

/**
 * T30 / issue #82 review follow-up (Finding 1): the previous single
 * headline ("N itens protegidos") summed `occurrence_count` over EVERY
 * category regardless of outcome -- including `preserved` ones (sent to
 * the provider unchanged) and any outcome this UI does not recognize --
 * which misrepresented what actually happened and violated the fail-closed
 * convention `lib/outcomes.ts` establishes for unknown outcomes.
 *
 * This instead groups `occurrence_count` by the SAME fail-closed
 * `describeCategoryOutcome(category, copy)` label every per-category row
 * already renders -- presenting an existing mapping, never re-deriving
 * boundary semantics from the raw outcome code -- in the canonical order
 * `KNOWN_DISCLOSURE_OUTCOMES` already defines (removed, pseudonymized,
 * generalized, preserved, blocked), with a final "unknown" bucket for any
 * outcome `describeCategoryOutcome` did not recognize. An unknown outcome
 * therefore always renders under its own unknown/"verify" label and can
 * never be folded into a protective group.
 */
function buildProtectionsBreakdown(categories: CategoryDisclosureSummary[], copy: AppCopy): string | null {
  if (categories.length === 0) {
    return null;
  }

  const counts = new Map<KnownDisclosureOutcome | "unknown", number>();
  for (const category of categories) {
    const descriptor = describeCategoryOutcome(category, copy);
    const key: KnownDisclosureOutcome | "unknown" = descriptor.known
      ? (category.outcome as KnownDisclosureOutcome)
      : "unknown";
    counts.set(key, (counts.get(key) ?? 0) + category.occurrence_count);
  }

  const orderedKeys: (KnownDisclosureOutcome | "unknown")[] = [...KNOWN_DISCLOSURE_OUTCOMES, "unknown"];
  const parts = orderedKeys
    .map((key) => {
      const count = counts.get(key);
      if (!count) {
        return null;
      }
      const label = key === "unknown" ? copy.outcomes.unknown.label : copy.outcomes[key].label;
      return `${label}: ${count}`;
    })
    .filter((part): part is string => part !== null);

  return parts.length > 0 ? parts.join(" · ") : null;
}

/**
 * T30 / issue #82 review follow-up (Finding 1): `ReconstructionStage` never
 * reports HOW MANY pseudonyms were reconstructed -- only `attempted`,
 * `reconstructed_hash`, and `changed_from_provider_response`. A pseudonym
 * the model never echoed back was never "reconstructed", so this renders a
 * plain, count-free statement, and only when the API affirmatively says
 * the final answer actually differed from the provider's raw response
 * after local reconstruction (`attempted && changed_from_provider_response
 * === true`). `attempted` alone (with `changed` false or unknown/`null`)
 * proves nothing was reconstructed, so it renders nothing rather than
 * invent a claim.
 */
function buildReconstructionNote(reconstruction: ReconstructionStage, copy: AppCopy): string | null {
  if (!reconstruction.attempted || reconstruction.changed_from_provider_response !== true) {
    return null;
  }
  return copy.result.reconstructionApplied;
}

export interface ResultScreenProps {
  execute: ExecuteResponse;
  health: ProviderModeState;
  /** Set when the last "Comparar estratégias" request failed; safe/generic only. */
  compareError: DisplayError | null;
  onRestart: () => void;
  /**
   * Always available -- comparison is offered regardless of whether this
   * particular execution was blocked, failed, or succeeded (T21/#29: the
   * screen exists to explain the mechanism, not just a successful run).
   */
  onCompareStrategies: () => void;
  /**
   * Opens "Ver detalhes técnicos" (T21/#29 third slice) -- always available,
   * same posture as `onCompareStrategies`, since the technical view exists
   * to explain what actually ran regardless of the outcome.
   */
  onViewTechnicalDetails: () => void;
  /**
   * T29 / issue #72, same posture as `ReviewScreen`'s prop of the same
   * name: a UX convenience fetched once, up front, by `GuidedFlow` via
   * `getDemoFeatures`. Defaults to `false` (disabled) so existing
   * callers/tests are unaffected.
   */
  demoVaultExplorerEnabled?: boolean;
  /**
   * The SAME preview's `vault_explorer_token` this execution's confirmed
   * review carried -- `ExecuteResponse` itself has no such field (only the
   * preview step ever issues a token), so this is threaded through
   * separately rather than added to `ExecuteResponse`. `null` when the
   * flag is off, when the caller has no preview to hand (existing
   * callers/tests), or when the decision had no explorable reference.
   */
  vaultExplorerToken?: string | null;
}

export function ResultScreen({
  execute,
  health,
  compareError,
  onRestart,
  onCompareStrategies,
  onViewTechnicalDetails,
  demoVaultExplorerEnabled = false,
  vaultExplorerToken = null,
}: ResultScreenProps) {
  const copy = useCopy();
  const [whatHappenedOpen, setWhatHappenedOpen] = useState(false);
  const isBlocked = execute.summary.status === "blocked";
  const providerFailed = execute.provider.failed;
  const providerModeNotice = describeProviderMode(health, copy);
  const protectionsBreakdown = buildProtectionsBreakdown(execute.summary.categories, copy);
  const reconstructionNote = buildReconstructionNote(execute.reconstruction, copy);

  return (
    <section aria-labelledby="result-heading" className={styles.section}>
      <h1 id="result-heading" className={styles.heading}>
        {copy.result.heading}
      </h1>

      {providerModeNotice && (
        <p
          role="status"
          className={`${styles.providerModeNotice} ${
            providerModeNotice.tone === "unverified" ? styles.unverifiedModeLabel : styles.demoLabel
          }`}
        >
          {providerModeNotice.message}
        </p>
      )}

      {isBlocked ? (
        <div role="alert" className={styles.blocked}>
          <h2>{copy.result.blockedHeading}</h2>
          <p>{copy.result.blockedExplanation}</p>
        </div>
      ) : providerFailed ? (
        <div role="alert" className={styles.providerFailed}>
          <h2>{copy.result.providerFailedHeading}</h2>
          <p>{copy.result.providerFailedExplanation}</p>
          {execute.provider.failure_kind && <p>{execute.provider.failure_kind}</p>}
        </div>
      ) : (
        <div>
          <h2 className={styles.subheading}>{copy.sectionHeadings.finalAnswer}</h2>
          <p className={styles.finalAnswer}>{execute.final_answer}</p>
        </div>
      )}

      <div>
        <h2 className={styles.subheading}>{copy.result.protectionsAppliedHeading}</h2>
        {execute.summary.categories.length === 0 ? (
          <p>{copy.review.noneDetected}</p>
        ) : (
          <>
            {protectionsBreakdown && <p className={styles.protectionsSummary}>{protectionsBreakdown}</p>}
            {reconstructionNote && <p className={styles.explanation}>{reconstructionNote}</p>}
            <ul className={styles.protectionsList}>
              {execute.summary.categories.map((category) => {
                const descriptor = describeCategoryOutcome(category, copy);
                // Same presentation mapping the review step used, so the two
                // screens never name the same category two different ways.
                // The raw identifier stays the React key, never the label.
                const categoryDescriptor = describeCategory(category.category, copy);
                return (
                  <li key={category.category}>
                    {categoryDescriptor.label}: {descriptor.label}
                  </li>
                );
              })}
            </ul>
          </>
        )}
      </div>

      <details
        className={styles.levelDisclosure}
        open={whatHappenedOpen}
        onToggle={(event) => setWhatHappenedOpen(event.currentTarget.open)}
      >
        <summary>{copy.result.whatHappenedToggle}</summary>
        {whatHappenedOpen && (
          <div>
            <p className={styles.explanation}>{copy.result.whatHappenedIntro}</p>
            <h3 className={styles.subheading}>{copy.result.pathHeading}</h3>
            <ol className={styles.path}>
              <li>{copy.result.pathLocal}</li>
              <li>{copy.result.pathProvider}</li>
              <li>{copy.result.pathLocal}</li>
            </ol>
          </div>
        )}
      </details>

      <div className={styles.secondarySection}>
        <h2 className={styles.subheading}>{copy.result.researchHeading}</h2>
        <p className={styles.explanation}>{copy.result.researchIntro}</p>
        <button type="button" className={styles.compareButton} onClick={onCompareStrategies}>
          {copy.buttons.compareStrategies}
        </button>
        {compareError && (
          <p role="alert" className={styles.error}>
            {compareError.message}
          </p>
        )}
      </div>

      <div className={styles.secondarySection}>
        <h2 className={styles.subheading}>{copy.result.technicalToolsHeading}</h2>
        <p className={styles.explanation}>{copy.result.technicalToolsIntro}</p>
        <button type="button" className={styles.compareButton} onClick={onViewTechnicalDetails}>
          {copy.buttons.viewTechnicalDetails}
        </button>
        {demoVaultExplorerEnabled && <VaultExplorerPanel token={vaultExplorerToken} />}
      </div>

      <div className={styles.actions}>
        <button type="button" className={styles.restartButton} onClick={onRestart}>
          {copy.result.restart}
        </button>
      </div>
    </section>
  );
}
