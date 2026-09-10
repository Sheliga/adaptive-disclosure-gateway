"use client";

/**
 * "Comparação B0-B4" -- T21 / issue #29's second slice. Reached from Result
 * via `copy.buttons.compareStrategies`; renders a `CompareResponse`
 * (`POST /disclosure/compare`) as a teaching surface for someone who does
 * not know B0-B4 yet, not as a benchmark.
 *
 * Three properties this component is written to hold, each pinned by
 * `ComparisonScreen.test.tsx`:
 *
 *  - Entries render in EXACTLY the order `comparison.entries` arrives in.
 *    The API already returns `CANONICAL_COMPARISON_ORDER`
 *    (DIRECT -> STATIC_SANITIZATION -> REVERSIBLE_PSEUDONYMIZATION ->
 *    TASK_AWARE -> POLICY_GOVERNED); re-sorting here would be exactly the
 *    "UI reimplements semantics" mistake CLAUDE.md forbids, so this module
 *    never sorts, filters or reorders `entries`.
 *  - The B0 -- Direct warning is derived from `entry.unsafe_control_baseline`
 *    ONLY, never from `entry.strategy === "b0"`. A future unsafe-control
 *    treatment that is not B0, or a B0 entry that stopped being the unsafe
 *    control, must both be handled correctly without this file changing.
 *  - `entry.external_payload` is kept OUT of the React tree (not merely
 *    hidden by CSS) until its own `<details>` is opened -- the same pattern
 *    `ReviewScreen` uses for the preview payload, applied per-entry here
 *    since a comparison holds five of them.
 *
 * Human language dominates: the visible headline for every entry is
 * `copy.treatments[strategy].name` (a plain-language treatment name), never
 * the raw `b0`-`b4` code or the raw `treatment` identifier -- those stay in
 * the per-entry technical-details disclosure. Category outcomes reuse
 * `CategoryOutcomeRow`/`describeCategoryOutcome`/`describeCategory`
 * unchanged, so this screen never re-derives the local-vs-sent split or the
 * outcome vocabulary Review/Result already established.
 *
 * No aggregate/derived scientific content is computed here: no counts
 * across entries, no scores, no ranking beyond the pre-existing
 * `recommended` product flag, and nothing from `experiments.scoring` or the
 * oracle is imported or reproduced -- see `application/contracts.py`'s
 * `StrategyComparisonEntry` docstring for why that boundary exists on the
 * API side already.
 */

import { useState } from "react";

import type { CompareResponse, StrategyComparisonEntry } from "@/lib/contracts";
import { copy } from "@/lib/copy";

import { CategoryOutcomeRow } from "../CategoryOutcomeRow/CategoryOutcomeRow";
import styles from "./ComparisonScreen.module.css";

export interface ComparisonScreenProps {
  comparison: CompareResponse;
  onBack: () => void;
}

export function ComparisonScreen({ comparison, onBack }: ComparisonScreenProps) {
  return (
    <section aria-labelledby="comparison-heading" className={styles.section}>
      <h1 id="comparison-heading" className={styles.heading}>
        {copy.comparison.heading}
      </h1>
      <p>{copy.comparison.intro}</p>
      <p role="status" className={styles.simulationNotice}>
        {copy.comparison.simulationNotice}
      </p>

      <div className={styles.entries}>
        {comparison.entries.map((entry) => (
          <ComparisonEntryCard key={entry.strategy} entry={entry} />
        ))}
      </div>

      <button type="button" className={styles.backButton} onClick={onBack}>
        {copy.comparison.backToResult}
      </button>
    </section>
  );
}

function treatmentCopyFor(strategy: string): { name: string; description: string } {
  const known = copy.treatments[strategy];
  // Fail-closed presentation, same posture as `describeCategory`: an
  // unrecognized strategy code shows itself honestly rather than a made-up
  // name -- this only happens if a future strategy is added API-side before
  // this UI knows about it.
  return known ?? { name: strategy, description: "" };
}

function ComparisonEntryCard({ entry }: { entry: StrategyComparisonEntry }) {
  const [payloadOpen, setPayloadOpen] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);

  const treatmentCopy = treatmentCopyFor(entry.strategy);
  const categories = entry.summary.categories;
  const localCategories = categories.filter((category) => !category.crosses_trust_boundary);
  const sentCategories = categories.filter((category) => category.crosses_trust_boundary);

  return (
    <article className={styles.card}>
      <div className={styles.cardHeader}>
        <h2 className={styles.strategyName}>{treatmentCopy.name}</h2>
        {entry.recommended && <span className={styles.recommendedBadge}>{copy.comparison.recommendedBadge}</span>}
      </div>

      {treatmentCopy.description && <p className={styles.strategyDescription}>{treatmentCopy.description}</p>}

      {entry.unsafe_control_baseline && (
        <div role="alert" className={styles.unsafeControl}>
          <h3>{copy.comparison.unsafeControlHeading}</h3>
          <p>{copy.comparison.unsafeControlExplanation}</p>
        </div>
      )}

      <div>
        {categories.length === 0 ? (
          <p>{copy.review.noneDetected}</p>
        ) : (
          <p>
            {entry.summary.detected_span_count} {copy.comparison.categoriesDetectedLabel}
          </p>
        )}
      </div>

      <div>
        <h3 className={styles.sectionHeading}>{copy.sectionHeadings.whatStaysLocal}</h3>
        {localCategories.length === 0 ? (
          <p>{copy.review.nothingInSection}</p>
        ) : (
          <ul className={styles.list}>
            {localCategories.map((category) => (
              <CategoryOutcomeRow key={category.category} category={category} />
            ))}
          </ul>
        )}
      </div>

      <div>
        <h3 className={styles.sectionHeading}>{copy.sectionHeadings.whatWasSent}</h3>
        {sentCategories.length === 0 ? (
          <p>{copy.review.nothingInSection}</p>
        ) : (
          <ul className={styles.list}>
            {sentCategories.map((category) => (
              <CategoryOutcomeRow key={category.category} category={category} />
            ))}
          </ul>
        )}
      </div>

      <details open={payloadOpen} onToggle={(event) => setPayloadOpen(event.currentTarget.open)}>
        <summary>{copy.comparison.showPayloadToggle}</summary>
        {payloadOpen && (
          <>
            {entry.unsafe_control_baseline && <p>{copy.comparison.unsafeControlPayloadContext}</p>}
            <pre className={styles.payload}>{entry.external_payload}</pre>
            <p>
              {entry.payload_byte_count} {copy.review.payloadByteCountLabel}
            </p>
          </>
        )}
      </details>

      <details open={detailsOpen} onToggle={(event) => setDetailsOpen(event.currentTarget.open)}>
        <summary>{copy.comparison.technicalDetailsToggle}</summary>
        {detailsOpen && (
          <dl className={styles.technicalDetails}>
            <dt>{copy.comparison.strategyIdLabel}</dt>
            <dd>
              <code>{entry.strategy}</code>
            </dd>
            <dt>{copy.comparison.treatmentIdLabel}</dt>
            <dd>
              <code>{entry.treatment}</code>
            </dd>
          </dl>
        )}
      </details>
    </article>
  );
}
