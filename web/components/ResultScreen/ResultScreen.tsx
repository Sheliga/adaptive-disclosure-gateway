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
 * `health.provider.deterministic_demo_mode` drives the FakeProvider label
 * (issue #29: FakeProvider must be clearly labeled as a deterministic
 * demonstration provider, not a real model).
 */

import type { ExecuteResponse, HealthResponse } from "@/lib/contracts";
import { copy } from "@/lib/copy";
import { describeCategoryOutcome } from "@/lib/outcomes";

import styles from "./ResultScreen.module.css";

export interface ResultScreenProps {
  execute: ExecuteResponse;
  health: HealthResponse | null;
  onRestart: () => void;
}

export function ResultScreen({ execute, health, onRestart }: ResultScreenProps) {
  const isBlocked = execute.summary.status === "blocked";
  const providerFailed = execute.provider.failed;
  const isDeterministicDemo = health?.provider.deterministic_demo_mode === true;

  return (
    <section aria-labelledby="result-heading" className={styles.section}>
      <h1 id="result-heading" className={styles.heading}>
        {copy.result.heading}
      </h1>

      {isDeterministicDemo && (
        <p role="status" className={styles.demoLabel}>
          {copy.provider.deterministicDemoLabel}
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
              const descriptor = describeCategoryOutcome(category);
              return (
                <li key={category.category}>
                  {category.category}: {descriptor.label}
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <button type="button" className={styles.restartButton} onClick={onRestart}>
        {copy.result.restart}
      </button>
    </section>
  );
}
