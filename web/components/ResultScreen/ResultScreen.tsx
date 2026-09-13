/**
 * Screen 4 -- "Resultado" (`docs/advisor-demo.md`). The primary output is
 * the final reconstructed answer; a simple `Local -> Provedor externo ->
 * Local` path and a short protections summary sit alongside it.
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
 * conflating them made a failed check silently erase the indication.
 */

import { useCopy } from "@/i18n/useLocale";
import { describeCategory } from "@/lib/categoryLabels";
import type { DisplayError } from "@/lib/api";
import type { ExecuteResponse } from "@/lib/contracts";
import { describeCategoryOutcome } from "@/lib/outcomes";
import { describeProviderMode, type ProviderModeState } from "@/lib/providerMode";

import styles from "./ResultScreen.module.css";

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
}

export function ResultScreen({
  execute,
  health,
  compareError,
  onRestart,
  onCompareStrategies,
  onViewTechnicalDetails,
}: ResultScreenProps) {
  const copy = useCopy();
  const isBlocked = execute.summary.status === "blocked";
  const providerFailed = execute.provider.failed;
  const providerModeNotice = describeProviderMode(health, copy);

  return (
    <section aria-labelledby="result-heading" className={styles.section}>
      <h1 id="result-heading" className={styles.heading}>
        {copy.result.heading}
      </h1>

      {providerModeNotice && (
        <p
          role="status"
          className={
            providerModeNotice.tone === "unverified"
              ? styles.unverifiedModeLabel
              : styles.demoLabel
          }
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
        <h2 className={styles.subheading}>{copy.result.pathHeading}</h2>
        <ol className={styles.path}>
          <li>{copy.result.pathLocal}</li>
          <li>{copy.result.pathProvider}</li>
          <li>{copy.result.pathLocal}</li>
        </ol>
      </div>

      <div>
        <h2 className={styles.subheading}>{copy.result.protectionsAppliedHeading}</h2>
        {execute.summary.categories.length === 0 ? (
          <p>{copy.review.noneDetected}</p>
        ) : (
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
        )}
      </div>

      {compareError && (
        <p role="alert" className={styles.error}>
          {compareError.message}
        </p>
      )}

      <div className={styles.actions}>
        <button type="button" className={styles.restartButton} onClick={onRestart}>
          {copy.result.restart}
        </button>
        <button type="button" className={styles.compareButton} onClick={onCompareStrategies}>
          {copy.buttons.compareStrategies}
        </button>
        <button type="button" className={styles.compareButton} onClick={onViewTechnicalDetails}>
          {copy.buttons.viewTechnicalDetails}
        </button>
      </div>
    </section>
  );
}
