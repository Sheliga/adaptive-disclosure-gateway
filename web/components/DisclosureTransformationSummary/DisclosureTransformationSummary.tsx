"use client";

/**
 * T32.3 / issue #103 -- the primary before/after: "what the gateway did",
 * visible by default (no click) in Review, in the read-only Approved Review,
 * and inside the Result recap.
 *
 * SINGLE SOURCE. Built ONLY from `inspection.segments[]` (T27 / #69,
 * `application/inspection.py`), rendered in the exact order the backend
 * emits them. It never diffs strings, searches substrings, applies a regex
 * or infers an action from content: `action`/`category` are presented
 * exactly as the API sent them, through the SAME fail-closed mappings the
 * detailed inspector uses (`describeInspectionAction`, `describeCategory`).
 * `lib/responseGuards.ts` has already verified that the disclosed segments
 * join back to exactly THIS preview's `external_payload` -- i.e. the
 * disclosed side shown here is an exact view of what THIS preview computed.
 *
 * That is NOT the same guarantee as "exactly what crosses the boundary
 * later, at execute time" (#103 review, PR #108). For upload, it is: the
 * confirmation token binds `execute_document` to this exact preview, and
 * execute re-verifies the decision matches what was approved before it will
 * disclose anything. For paste/example, `executeDisclosure` independently
 * re-runs the decision (detector, task analyzer, decision phase) with no
 * token binding it to this preview, so the representation actually sent
 * later can differ from the one shown here. The copy (`copy.beforeAfter`)
 * is written to reflect only the guarantee that actually holds: "prepared"/
 * "reviewed", never a promise of byte-identity with the later execute call.
 *
 * DELIBERATELY NOT the `DisclosureInspector`. That component stays the
 * collapsed, secondary layer with technical reason, treatment, strategy and
 * per-segment ordinals. This one answers only: what was there, what changed,
 * what goes out -- so it shows no b0-b4 code, strategy, policy, reason, id or
 * ordinal, and no raw identifier is ever used as a label (an unknown action
 * or category renders its "not recognized" copy, never the raw value).
 *
 * A11Y. Reading order is Original -> local transformation -> sent. Colour is
 * never the only signal: every transformed passage carries a visible text
 * tag (the category on the original side, the action on the sent side), and
 * a removed passage shows the explicit removal marker in place of its empty
 * disclosed value. Segments are plain inline text -- nothing is focusable.
 *
 * UNAVAILABLE. `available: false` never produces a before/after: "blocked"
 * says nothing was released for sending (no "sent" column at all),
 * "alignment_failed" says the view could not be produced safely, and any
 * other reason fails closed to a neutral message. A `null` inspection (the
 * capability is off) is the caller's case: it renders nothing here.
 *
 * NO-LEAK. Segment values are rendered from props only: this component
 * writes nothing to the URL, history, storage, logs or telemetry.
 */

import { useId } from "react";

import { useCopy } from "@/i18n/useLocale";
import { describeCategory } from "@/lib/categoryLabels";
import type { DisclosureInspection, InspectionSegment } from "@/lib/contracts";
import type { AppCopy } from "@/lib/copy";
import { describeInspectionAction } from "@/lib/inspectionActions";

import styles from "./DisclosureTransformationSummary.module.css";

export type DisclosureTransformationSummaryVariant = "review" | "approved";

export interface DisclosureTransformationSummaryProps {
  inspection: DisclosureInspection;
  /** "review": what the gateway prepared for this preview, pending confirmation; "approved": what was presented for approval before the external call. Neither claims byte-identity with a later execute call (see this module's docstring). */
  variant: DisclosureTransformationSummaryVariant;
  /** `false` when embedded under a caller's own heading (the Result recap). */
  showHeading?: boolean;
}

/** Only these four actions have human copy; anything else is "unknown". */
function actionKey(segment: InspectionSegment): string | null {
  if (segment.action === null) {
    return null;
  }
  return describeInspectionAction(segment.action).known ? segment.action : "unknown";
}

function categoryLabel(segment: InspectionSegment, copy: AppCopy): string {
  // `category` is non-null whenever `action` is (responseGuards invariant);
  // the fallback still never shows a raw identifier.
  return segment.category !== null ? describeCategory(segment.category, copy).label : copy.categories.unrecognized;
}

/** A visible text tag; the parentheses exist only for assistive technology. */
function Tag({ label }: { label: string }) {
  return (
    <span className={styles.tag}>
      <span className={styles.visuallyHidden}> (</span>
      {label}
      <span className={styles.visuallyHidden}>)</span>
    </span>
  );
}

function OriginalSegment({ segment, copy }: { segment: InspectionSegment; copy: AppCopy }) {
  const key = actionKey(segment);
  if (key === null) {
    return <span data-segment-text="">{segment.original}</span>;
  }
  return (
    <mark className={styles.mark} data-action={key}>
      <span data-segment-text="">{segment.original}</span>
      <Tag label={categoryLabel(segment, copy)} />
    </mark>
  );
}

function DisclosedSegment({ segment, copy }: { segment: InspectionSegment; copy: AppCopy }) {
  const key = actionKey(segment);
  if (key === null) {
    return <span data-segment-text="">{segment.disclosed}</span>;
  }
  if (key === "remove") {
    return (
      <mark className={`${styles.mark} ${styles.removed}`} data-action={key}>
        <span data-segment-text="">{copy.inspectionActions.removedMarker}</span>
      </mark>
    );
  }
  return (
    <mark className={styles.mark} data-action={key}>
      <span data-segment-text="">{segment.disclosed}</span>
      <Tag label={describeInspectionAction(segment.action, copy).label} />
    </mark>
  );
}

function unavailableMessage(reason: string | null, copy: AppCopy): string {
  if (reason === "blocked") {
    return copy.beforeAfter.unavailableBlocked;
  }
  if (reason === "alignment_failed") {
    return copy.beforeAfter.unavailableAlignmentFailed;
  }
  return copy.beforeAfter.unavailableUnknown;
}

export function DisclosureTransformationSummary({
  inspection,
  variant,
  showHeading = true,
}: DisclosureTransformationSummaryProps) {
  const copy = useCopy();
  const headingId = useId();
  const heading = showHeading ? (
    <h2 id={headingId} className={styles.heading}>
      {copy.beforeAfter.heading}
    </h2>
  ) : null;

  if (!inspection.available) {
    return (
      <section
        className={styles.summary}
        aria-labelledby={showHeading ? headingId : undefined}
        data-testid="before-after-summary"
      >
        {heading}
        <p role="note">{unavailableMessage(inspection.unavailable_reason, copy)}</p>
      </section>
    );
  }

  const segments = inspection.segments;
  const handled = segments.filter((segment) => segment.action !== null).length;
  const disclosedHeading =
    variant === "review" ? copy.beforeAfter.disclosedHeadingReview : copy.beforeAfter.disclosedHeadingApproved;
  const disclosedCaption =
    variant === "review" ? copy.beforeAfter.disclosedCaptionReview : copy.beforeAfter.disclosedCaptionApproved;

  return (
    <section
      className={styles.summary}
      aria-labelledby={showHeading ? headingId : undefined}
      data-testid="before-after-summary"
    >
      {heading}
      <p className={styles.intro}>{copy.beforeAfter.intro}</p>
      <p className={styles.count}>
        {handled === 0 ? copy.beforeAfter.noChanges : copy.beforeAfter.handledCount.replace("{n}", String(handled))}
      </p>

      <div className={styles.comparison}>
        <div className={styles.side}>
          <h3 className={styles.sideHeading}>{copy.beforeAfter.originalHeading}</h3>
          <p className={styles.caption}>{copy.beforeAfter.originalCaption}</p>
          <div className={styles.text} data-testid="before-after-original">
            {segments.map((segment, index) => (
              <OriginalSegment key={index} segment={segment} copy={copy} />
            ))}
          </div>
        </div>

        <p className={styles.step}>
          <span aria-hidden="true" className={styles.arrow} />
          {copy.beforeAfter.transformationStep}
        </p>

        <div className={styles.side}>
          <h3 className={styles.sideHeading}>{disclosedHeading}</h3>
          <p className={styles.caption}>{disclosedCaption}</p>
          <div className={`${styles.text} ${styles.disclosedText}`} data-testid="before-after-disclosed">
            {segments.map((segment, index) => (
              <DisclosedSegment key={index} segment={segment} copy={copy} />
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
