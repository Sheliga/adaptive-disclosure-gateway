"use client";

/**
 * The Level-1 disclosure overview (T30 / issue #82), extracted unchanged
 * from `ReviewScreen` so the read-only Approved Review (T32.2 / #102) shows
 * exactly the same reviewed facts: what was detected, what stays local and
 * what crosses the trust boundary, including the payload disclosure.
 *
 * The local-vs-sent split is computed from `category.crosses_trust_boundary`
 * ONLY (see `ReviewScreen`'s docstring), and `external_payload` stays OUT of
 * the React tree until its own toggle has been opened.
 */

import { useState } from "react";

import { useCopy } from "@/i18n/useLocale";
import type { PreviewResponse } from "@/lib/contracts";

import { CategoryOutcomeRow } from "../CategoryOutcomeRow/CategoryOutcomeRow";
import styles from "./ReviewScreen.module.css";

export interface DisclosureOverviewProps {
  preview: PreviewResponse;
  /** Heading over the boundary-crossing section; forward-looking on the live Review. */
  sentHeading: string;
  payloadToggleLabel: string;
}

export function DisclosureOverview({ preview, sentHeading, payloadToggleLabel }: DisclosureOverviewProps) {
  const copy = useCopy();
  const [payloadOpen, setPayloadOpen] = useState(false);

  const isBlocked = preview.summary.status === "blocked";
  const categories = preview.summary.categories;
  const localCategories = categories.filter((category) => !category.crosses_trust_boundary);
  const sentCategories = categories.filter((category) => category.crosses_trust_boundary);

  return (
    <>
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
        <h2 className={styles.subheading}>{sentHeading}</h2>
        {sentCategories.length === 0 ? (
          <p>{copy.review.nothingInSection}</p>
        ) : (
          <ul className={styles.list}>
            {sentCategories.map((category) => (
              <CategoryOutcomeRow key={category.category} category={category} />
            ))}
          </ul>
        )}

        <details open={payloadOpen} onToggle={(event) => setPayloadOpen(event.currentTarget.open)}>
          <summary>{payloadToggleLabel}</summary>
          {payloadOpen && (
            <>
              <pre className={styles.payload}>{preview.external_payload}</pre>
              <p>
                {preview.payload_byte_count} {copy.review.payloadByteCountLabel}
              </p>
            </>
          )}
        </details>
      </div>
    </>
  );
}
