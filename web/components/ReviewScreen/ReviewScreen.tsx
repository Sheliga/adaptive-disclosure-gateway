"use client";

/**
 * Screen 3 -- "Revisão antes do envio" (`docs/advisor-demo.md`). This
 * screen is the whole point of the product: it exists so nothing reaches
 * the external provider before the reviewer has seen and confirmed it.
 *
 * The local-vs-sent split is computed from `category.crosses_trust_boundary`
 * ONLY (never re-derived from the outcome code) -- see `lib/outcomes.ts`'s
 * docstring for why re-deriving it here would be exactly the "UI
 * reimplements security semantics" mistake CLAUDE.md forbids.
 *
 * `external_payload` is rendered only once the disclosure `<details>`
 * control has actually been opened -- it is intentionally kept out of the
 * React tree (not just visually hidden) until then, so "not shown by
 * default" is literally true of the DOM, not just of the stylesheet.
 *
 * A `blocked` summary renders no confirm action at all: there is no path
 * from this screen to `onConfirm` when `preview.summary.status ===
 * "blocked"`.
 */

import { useState } from "react";

import type { DisplayError } from "@/lib/api";
import type { PreviewResponse } from "@/lib/contracts";
import { copy } from "@/lib/copy";

import { CategoryOutcomeRow } from "../CategoryOutcomeRow/CategoryOutcomeRow";
import styles from "./ReviewScreen.module.css";

export interface ReviewScreenProps {
  preview: PreviewResponse;
  executeError: DisplayError | null;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ReviewScreen({ preview, executeError, onConfirm, onCancel }: ReviewScreenProps) {
  const [payloadOpen, setPayloadOpen] = useState(false);

  const isBlocked = preview.summary.status === "blocked";
  const categories = preview.summary.categories;
  const localCategories = categories.filter((category) => !category.crosses_trust_boundary);
  const sentCategories = categories.filter((category) => category.crosses_trust_boundary);

  return (
    <section aria-labelledby="review-heading" className={styles.section}>
      <h1 id="review-heading" className={styles.heading}>
        {copy.review.heading}
      </h1>

      <div>
        <h2 className={styles.subheading}>{copy.sectionHeadings.whatWasDetected}</h2>
        {categories.length === 0 ? (
          <p>{copy.review.noneDetected}</p>
        ) : (
          <p>
            {preview.summary.detected_span_count} {copy.review.detectedCountLabel}
          </p>
        )}
      </div>

      {isBlocked && (
        <div role="alert" className={styles.blocked}>
          <h2>{copy.review.blockedHeading}</h2>
          <p>{copy.review.blockedExplanation}</p>
        </div>
      )}

      <div>
        <h2 className={styles.subheading}>{copy.sectionHeadings.whatStaysLocal}</h2>
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
        <h2 className={styles.subheading}>{copy.sectionHeadings.whatWasSent}</h2>
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
        <summary>{copy.review.showPayloadToggle}</summary>
        {payloadOpen && (
          <>
            <pre className={styles.payload}>{preview.external_payload}</pre>
            <p>
              {preview.payload_byte_count} {copy.review.payloadByteCountLabel}
            </p>
          </>
        )}
      </details>

      {executeError && (
        <p role="alert" className={styles.error}>
          {executeError.message}
        </p>
      )}

      <div className={styles.actions}>
        <button type="button" className={styles.cancelButton} onClick={onCancel}>
          {copy.review.backToCompose}
        </button>
        {!isBlocked && (
          <button type="button" className={styles.confirmButton} onClick={onConfirm}>
            {copy.review.confirmSend}
          </button>
        )}
      </div>
    </section>
  );
}
