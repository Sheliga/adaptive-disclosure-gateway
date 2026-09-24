"use client";

/**
 * T27 / issue #69 -- the transformation inspector: a side-by-side
 * original/disclosed comparison of `preview.inspection`, rendered from
 * `ReviewScreen` only when `preview.inspection !== null`.
 *
 * Collapsed by default behind a `<details>` control, and its content is
 * kept OUT of the React tree (not merely visually hidden) until opened --
 * the same pattern `ReviewScreen` already uses for `external_payload`.
 *
 * Segments are keyed by their ARRAY INDEX, never by their text: the same
 * original string can appear more than once with different categories/
 * actions (or as an untouched occurrence elsewhere), and `application/
 * inspection.py` already guarantees `join(original)`/`join(disclosed)`
 * reconstruct the analyzed text/`external_payload` exactly in order -- this
 * component only ever renders that order, never re-sorts or deduplicates
 * it.
 *
 * A `remove`d segment's DISCLOSED side shows an explicit, visible "removed"
 * marker (`copy.inspectionActions.removedMarker`) instead of the segment's
 * real (empty) `disclosed` value -- that substitution is presentation only.
 * The unmodified payload remains available through `ReviewScreen`'s own
 * payload disclosure (`copy.review.showPayloadToggle`).
 *
 * The transformation itself (category/action/reason) is never re-derived
 * here: `action`/`category` are rendered exactly as the API sent them
 * through `lib/inspectionActions.ts`/`lib/categoryLabels.ts`'s fail-closed
 * mappings, and `technical_reason` is looked up from the SAME
 * `preview.summary.categories` this screen already renders elsewhere --
 * never a second, inspector-specific reason computed independently.
 */

import { useState } from "react";

import { useCopy } from "@/i18n/useLocale";
import { describeCategory } from "@/lib/categoryLabels";
import type { CategoryDisclosureSummary, DisclosureInspection, InspectionSegment } from "@/lib/contracts";
import type { AppCopy } from "@/lib/copy";
import { describeInspectionAction } from "@/lib/inspectionActions";

import styles from "./DisclosureInspector.module.css";

export interface DisclosureInspectorProps {
  inspection: DisclosureInspection;
  categories: CategoryDisclosureSummary[];
  treatment: string;
  strategy: string;
}

const LEGEND_ACTIONS = ["preserve", "pseudonymize", "generalize", "remove"] as const;

function treatmentNameFor(treatment: string, copy: AppCopy): string {
  // Fail-closed presentation, same posture as ComparisonScreen's
  // treatmentCopyFor: an unrecognized code shows itself honestly.
  return copy.treatments[treatment]?.name ?? treatment;
}

function formatPosition(template: string, ordinal: number, total: number): string {
  return template.replace("{n}", String(ordinal)).replace("{total}", String(total));
}

interface SegmentMarkProps {
  text: string;
  action: string | null;
  ordinal: number | null;
  categoryLabel: string | null;
  selected: boolean;
  removedMarker: boolean;
  onSelect: () => void;
}

/**
 * Renders one segment's text on one side. Untouched segments (`action ===
 * null`) are a plain, non-interactive `<span>` -- exactly the raw text, no
 * badge, no button semantics. A transformed segment is a focusable,
 * clickable `<button>` whose own text content is EXACTLY the text passed in
 * (never a badge/glyph character appended to it) -- `data-ordinal`/
 * `data-action` drive the CSS-rendered ordinal badge and glyph, and
 * `aria-label` carries the same information as the accessible name, so
 * removing the CSS never removes the information, only its visual
 * presentation.
 */
function SegmentMark({
  text,
  action,
  ordinal,
  categoryLabel,
  selected,
  removedMarker,
  onSelect,
}: SegmentMarkProps) {
  if (action === null) {
    return <span className={styles.untouched}>{text}</span>;
  }
  const ariaLabel = `${ordinal ?? ""}: ${action}${categoryLabel ? ` — ${categoryLabel}` : ""}`;
  return (
    <button
      type="button"
      className={[styles.segment, selected ? styles.segmentSelected : "", removedMarker ? styles.removedSegment : ""]
        .filter(Boolean)
        .join(" ")}
      data-ordinal={ordinal ?? undefined}
      data-action={action}
      aria-pressed={selected}
      aria-label={ariaLabel}
      onClick={onSelect}
    >
      {text}
    </button>
  );
}

export function DisclosureInspector({ inspection, categories, treatment, strategy }: DisclosureInspectorProps) {
  const copy = useCopy();
  const [open, setOpen] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);

  if (!inspection.available) {
    const isBlocked = inspection.unavailable_reason === "blocked";
    return (
      <div className={styles.details} role="note">
        <h3>
          {isBlocked
            ? copy.disclosureInspector.unavailableBlockedHeading
            : copy.disclosureInspector.unavailableAlignmentFailedHeading}
        </h3>
        <p>
          {isBlocked
            ? copy.disclosureInspector.unavailableBlockedExplanation
            : copy.disclosureInspector.unavailableAlignmentFailedExplanation}
        </p>
      </div>
    );
  }

  const segments = inspection.segments;
  const ordinals: (number | null)[] = [];
  let runningOrdinal = 0;
  for (const seg of segments) {
    if (seg.action !== null) {
      runningOrdinal += 1;
      ordinals.push(runningOrdinal);
    } else {
      ordinals.push(null);
    }
  }
  const totalTransformed = runningOrdinal;

  const selectedSegment: InspectionSegment | null = selectedIndex !== null ? segments[selectedIndex] : null;
  const selectedOrdinal = selectedIndex !== null ? ordinals[selectedIndex] : null;
  const selectedActionDescriptor = selectedSegment
    ? describeInspectionAction(selectedSegment.action, copy)
    : null;
  const selectedCategoryDescriptor =
    selectedSegment && selectedSegment.category !== null
      ? describeCategory(selectedSegment.category, copy)
      : null;
  const matchingCategorySummary =
    selectedSegment && selectedSegment.category !== null
      ? (categories.find((entry) => entry.category === selectedSegment.category) ?? null)
      : null;

  return (
    <details open={open} onToggle={(event) => setOpen(event.currentTarget.open)} className={styles.details}>
      <summary>{copy.disclosureInspector.toggleLabel}</summary>
      {open && (
        <div className={styles.content}>
          <h3>{copy.disclosureInspector.heading}</h3>
          <p className={styles.disclaimer}>{copy.disclosureInspector.disclaimer}</p>

          <div className={styles.legend}>
            <h4>{copy.disclosureInspector.legendHeading}</h4>
            <ul>
              {LEGEND_ACTIONS.map((action) => {
                const descriptor = describeInspectionAction(action, copy);
                return (
                  <li key={action}>
                    <span aria-hidden="true" className={styles.legendGlyph} data-glyph={descriptor.glyph} />
                    {descriptor.label}
                  </li>
                );
              })}
            </ul>
          </div>

          <div className={styles.columns}>
            <div>
              <h4>{copy.disclosureInspector.originalColumnHeading}</h4>
              <div className={styles.text} data-testid="inspector-original-column">
                {segments.map((segment, index) => {
                  const categoryLabel =
                    segment.category !== null ? describeCategory(segment.category, copy).label : null;
                  return (
                    <SegmentMark
                      key={index}
                      text={segment.original}
                      action={segment.action}
                      ordinal={ordinals[index]}
                      categoryLabel={categoryLabel}
                      selected={selectedIndex === index}
                      removedMarker={false}
                      onSelect={() => setSelectedIndex(index)}
                    />
                  );
                })}
              </div>
            </div>
            <div>
              <h4>{copy.disclosureInspector.disclosedColumnHeading}</h4>
              <div className={styles.text} data-testid="inspector-disclosed-column">
                {segments.map((segment, index) => {
                  const isRemoved = segment.action === "remove";
                  const categoryLabel =
                    segment.category !== null ? describeCategory(segment.category, copy).label : null;
                  return (
                    <SegmentMark
                      key={index}
                      text={isRemoved ? copy.inspectionActions.removedMarker : segment.disclosed}
                      action={segment.action}
                      ordinal={ordinals[index]}
                      categoryLabel={categoryLabel}
                      selected={selectedIndex === index}
                      removedMarker={isRemoved}
                      onSelect={() => setSelectedIndex(index)}
                    />
                  );
                })}
              </div>
            </div>
          </div>

          <div className={styles.detailPanel} aria-live="polite" data-testid="inspector-detail-panel">
            <h4>{copy.disclosureInspector.detailPanelHeading}</h4>
            {!selectedSegment && <p>{copy.disclosureInspector.noSelectionHint}</p>}
            {selectedSegment && selectedActionDescriptor && (
              <dl>
                <dt>{copy.disclosureInspector.detailActionLabel}</dt>
                <dd>
                  <span className={styles.detailValue}>{selectedActionDescriptor.label}</span>
                  <p className={styles.explanation}>{selectedActionDescriptor.explanation}</p>
                </dd>

                <dt>{copy.disclosureInspector.detailCategoryLabel}</dt>
                <dd>
                  <span className={styles.detailValue}>
                    {selectedCategoryDescriptor ? selectedCategoryDescriptor.label : copy.categories.unrecognized}
                  </span>
                  {selectedCategoryDescriptor && !selectedCategoryDescriptor.known && (
                    <>
                      {" "}
                      <code>{selectedCategoryDescriptor.technicalId}</code>
                    </>
                  )}
                </dd>

                <dt>{copy.disclosureInspector.detailTreatmentLabel}</dt>
                <dd>
                  <code>{treatment}</code> {treatmentNameFor(treatment, copy)}
                </dd>

                <dt>{copy.disclosureInspector.detailStrategyLabel}</dt>
                <dd>
                  <code>{strategy}</code>
                </dd>

                <dt>{copy.disclosureInspector.detailReasonLabel}</dt>
                <dd>
                  {matchingCategorySummary
                    ? matchingCategorySummary.technical_reason
                    : copy.disclosureInspector.detailReasonUnavailable}
                </dd>

                <dt>{copy.disclosureInspector.detailOriginalLabel}</dt>
                <dd className={styles.excerpt}>{selectedSegment.original}</dd>

                <dt>{copy.disclosureInspector.detailDisclosedLabel}</dt>
                <dd className={styles.excerpt}>{selectedSegment.disclosed}</dd>
              </dl>
            )}
            {selectedSegment && selectedOrdinal !== null && (
              <p className={styles.position}>
                {formatPosition(copy.disclosureInspector.detailPositionLabel, selectedOrdinal, totalTransformed)}
              </p>
            )}
          </div>
        </div>
      )}
    </details>
  );
}
