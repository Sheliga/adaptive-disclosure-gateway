"use client";

/**
 * "What you asked for" (T32.2 / #102): re-presents the retained
 * `ComposeState` before any disclosure detail, so the Review answers "what
 * am I about to send/process?" without the reviewer having to remember
 * Compose. Shared by the live Review and the read-only Approved Review.
 *
 * Only user-facing, already-visible selections are shown: the source kind,
 * the example's human label (via `describeExample`, raw id secondary only),
 * the uploaded file NAME, the human document/analysis type and the task.
 * Never the file's content, the pasted text itself, a confirmation token, a
 * hash or an internal id as primary information. Any value this UI has no
 * copy for renders the neutral `review.unknownValue` label -- never a raw
 * identifier and never an invented meaning (same fail-closed posture as
 * `lib/exampleLabels.ts` and `lib/categoryLabels.ts`).
 */

import type { ReactNode } from "react";

import { useCopy } from "@/i18n/useLocale";
import type { AppCopy } from "@/lib/copy";
import type { ExampleSummary } from "@/lib/contracts";
import { describeExample } from "@/lib/exampleLabels";
import type { ComposeState } from "@/lib/flow";

import styles from "./ReviewScreen.module.css";

export interface ReviewContextSummaryProps {
  compose: ComposeState;
  examples: readonly ExampleSummary[] | null;
  /** Optional action rendered inside the section (the live Review's "Change"). */
  action?: ReactNode;
}

function lookup(labels: Record<string, string>, key: string | null, fallback: string): string {
  if (key === null) {
    return fallback;
  }
  return Object.prototype.hasOwnProperty.call(labels, key) ? labels[key] : fallback;
}

function sourceLabel(compose: ComposeState, appCopy: AppCopy): string {
  switch (compose.mode) {
    case "example":
      return appCopy.review.sourceExample;
    case "upload":
      return appCopy.review.sourceUpload;
    case "paste":
      return appCopy.review.sourcePaste;
    default:
      return appCopy.review.unknownValue;
  }
}

export function ReviewContextSummary({ compose, examples, action }: ReviewContextSummaryProps) {
  const copy = useCopy();
  const task = compose.task.trim();

  const example =
    compose.mode === "example" && compose.exampleId !== null
      ? (examples ?? []).find((item) => item.example_id === compose.exampleId)
      : undefined;
  const descriptor = example !== undefined ? describeExample(example, examples ?? [], copy) : null;
  const exampleLabel =
    descriptor !== null && descriptor.known ? descriptor.label : copy.review.unknownValue;

  let taskValue: ReactNode;
  if (task.length > 0) {
    taskValue = task;
  } else if (compose.mode === "example" && example !== undefined && example.task.trim().length > 0) {
    taskValue = (
      <>
        {example.task} <span className={styles.explanation}>{copy.review.exampleSuggestedTask}</span>
      </>
    );
  } else if (compose.mode === "example") {
    taskValue = copy.review.unknownValue;
  } else {
    taskValue = copy.review.noTaskProvided;
  }

  return (
    <section aria-labelledby="review-context-heading" className={styles.context}>
      <h2 id="review-context-heading" className={styles.subheading}>
        {copy.review.contextHeading}
      </h2>
      <dl className={styles.contextList}>
        <dt className={styles.contextTerm}>{copy.review.sourceLabel}</dt>
        <dd>{sourceLabel(compose, copy)}</dd>

        {compose.mode === "example" && (
          <>
            <dt className={styles.contextTerm}>{copy.review.exampleLabel}</dt>
            <dd>
              <span>{exampleLabel}</span>
              {compose.exampleId !== null && (
                <span className={styles.explanation}>
                  {" "}
                  {copy.newTest.exampleTechnicalIdLabel} <code>{compose.exampleId}</code>
                </span>
              )}
            </dd>
          </>
        )}

        {compose.mode === "upload" && (
          <>
            <dt className={styles.contextTerm}>{copy.newTest.fileNameLabel}</dt>
            <dd>{compose.file?.filename ?? copy.review.unknownValue}</dd>
            <dt className={styles.contextTerm}>{copy.newTest.documentTypeLabel}</dt>
            <dd>{lookup(copy.newTest.documentTypeLabels, compose.documentType, copy.review.unknownValue)}</dd>
            <dt className={styles.contextTerm}>{copy.newTest.analysisModeLabel}</dt>
            <dd>{lookup(copy.newTest.analysisModeLabels, compose.analysisMode, copy.review.unknownValue)}</dd>
          </>
        )}

        <dt className={styles.contextTerm}>{copy.review.taskLabel}</dt>
        <dd>{taskValue}</dd>
      </dl>
      {action}
    </section>
  );
}
