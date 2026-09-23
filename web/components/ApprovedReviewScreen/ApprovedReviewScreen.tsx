"use client";

/**
 * The Approved Review (T32.2 / #102): the read-only, post-send view of the
 * Review a confirmed send came from. It is reached only by restoring the
 * "approvedReview" history snapshot (Result -> Back), and it renders over a
 * flow state that carries no confirmation token and whose reducer accepts no
 * send path (`lib/flow.ts`).
 *
 * Deliberately a separate component, not `ReviewScreen` with a flag: it has
 * no `onConfirm`/`onEdit` props at all, so there is no Confirm, no resend
 * and no "Change" that would imply altering the request already sent. The
 * only action is `onGoToResult`, which GuidedFlow wires to
 * `window.history.forward()` -- navigation over the existing Result
 * snapshot, never a new request. The research/technical tools (inspector,
 * export/restore, Vault Explorer) belong to the pre-send decision and are
 * not repeated here.
 */

import { useCopy } from "@/i18n/useLocale";
import type { ExampleSummary, PreviewResponse } from "@/lib/contracts";
import type { ComposeState } from "@/lib/flow";

import { DisclosureOverview } from "../ReviewScreen/DisclosureOverview";
import { ReviewContextSummary } from "../ReviewScreen/ReviewContextSummary";
import styles from "../ReviewScreen/ReviewScreen.module.css";

export interface ApprovedReviewScreenProps {
  compose: ComposeState;
  preview: PreviewResponse;
  examples: readonly ExampleSummary[] | null;
  onGoToResult: () => void;
}

export function ApprovedReviewScreen({ compose, preview, examples, onGoToResult }: ApprovedReviewScreenProps) {
  const copy = useCopy();

  return (
    <section aria-labelledby="approved-review-heading" className={styles.section}>
      <h1 id="approved-review-heading" className={styles.heading}>
        {copy.approvedReview.heading}
      </h1>
      <p className={styles.sentBadge}>{copy.approvedReview.sentBadge}</p>
      <p>{copy.approvedReview.readOnlyNotice}</p>

      <ReviewContextSummary compose={compose} examples={examples} />

      <DisclosureOverview
        preview={preview}
        sentHeading={copy.approvedReview.sentHeading}
        payloadToggleLabel={copy.approvedReview.payloadToggle}
      />

      <div className={styles.actions}>
        <button type="button" className={styles.cancelButton} onClick={onGoToResult}>
          {copy.approvedReview.goToResult}
        </button>
      </div>
    </section>
  );
}
