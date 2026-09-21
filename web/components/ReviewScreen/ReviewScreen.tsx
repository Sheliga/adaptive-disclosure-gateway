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
 *
 * T28 / issue #70: `ExportRestorePanel` renders only when BOTH
 * `demoTransparencyEnabled` is true (fetched once, up front, by
 * `GuidedFlow` via `getDemoFeatures` -- any failure or invalid body there
 * is already treated as disabled before it ever reaches this prop) AND
 * `preview.summary.status === "allowed"` -- exporting a blocked disclosure
 * makes no sense, and T26's export route independently refuses it anyway
 * (`ExportRefusedError`). This screen never re-fetches or re-checks the
 * feature flag itself; the server-side route gate
 * (`lib/demoTransparency.ts`) remains the actual security boundary
 * regardless of what this prop says.
 *
 * T30 / issue #82 restructured this screen into progressive-disclosure
 * levels, WITHOUT touching the confirmation-token/preview-execute binding
 * or any gating condition above -- only where each already-gated panel is
 * mounted in the JSX tree changed:
 *
 *  - Level 1 (always visible): what was detected, what stays local, and
 *    -- prominently, under `copy.review.willBeSentHeading` -- exactly what
 *    will cross the trust boundary, including the payload disclosure
 *    (still kept OUT of the DOM until its own toggle is opened, unchanged).
 *  - Level 2: the T27 transformation inspector, now itself behind an outer
 *    `copy.review.understandChangesToggle` disclosure -- so understanding
 *    *why* something changed is one click deeper than seeing *what* will be
 *    sent.
 *  - Level 3: the T28 export/restore panel and the T29 Vault Explorer,
 *    together behind one `copy.review.technicalToolsToggle` disclosure,
 *    collapsed by default -- framed explicitly as a research/technical
 *    surface. This wrapper itself is only rendered when at least one of the
 *    two panels would actually show something, so a deployment with both
 *    demo flags off renders no empty "technical tools" toggle at all.
 */

import { useState } from "react";

import { useCopy } from "@/i18n/useLocale";
import type { DisplayError } from "@/lib/api";
import type { PreviewResponse } from "@/lib/contracts";
import { initialComposeState, type ComposeState } from "@/lib/flow";

import { CategoryOutcomeRow } from "../CategoryOutcomeRow/CategoryOutcomeRow";
import { DisclosureInspector } from "../DisclosureInspector/DisclosureInspector";
import { ExportRestorePanel } from "../ExportRestorePanel/ExportRestorePanel";
import { VaultExplorerPanel } from "../VaultExplorerPanel/VaultExplorerPanel";
import styles from "./ReviewScreen.module.css";

export interface ReviewScreenProps {
  preview: PreviewResponse;
  executeError: DisplayError | null;
  onConfirm: () => void;
  onCancel: () => void;
  /**
   * The compose state this preview was built from -- threaded through only
   * for `ExportRestorePanel`. Optional, defaulting to the initial (example
   * mode) compose state, so existing callers/tests that never render the
   * panel (`demoTransparencyEnabled` false, the default) are unaffected.
   */
  compose?: ComposeState;
  /** T28 / issue #70. See this module's docstring. Defaults to `false` (disabled) so existing callers/tests are unaffected. */
  demoTransparencyEnabled?: boolean;
  /**
   * T29 / issue #72. Same posture as `demoTransparencyEnabled`: a UX
   * convenience fetched once, up front, by `GuidedFlow` via
   * `getDemoFeatures` -- any failure there is already treated as disabled
   * before it ever reaches this prop. When `true`, `VaultExplorerPanel` is
   * rendered below the T27 inspector regardless of `preview.summary.status`
   * -- unlike `ExportRestorePanel`, a blocked decision still legitimately
   * carries a `null` `vault_explorer_token` (see that field's own
   * docstring), which the panel itself renders as an "unavailable" note
   * rather than needing this screen to decide that. Defaults to `false`
   * (disabled) so existing callers/tests are unaffected.
   */
  demoVaultExplorerEnabled?: boolean;
}

export function ReviewScreen({
  preview,
  executeError,
  onConfirm,
  onCancel,
  compose = initialComposeState,
  demoTransparencyEnabled = false,
  demoVaultExplorerEnabled = false,
}: ReviewScreenProps) {
  const copy = useCopy();
  const [payloadOpen, setPayloadOpen] = useState(false);
  const [changesOpen, setChangesOpen] = useState(false);
  const [technicalToolsOpen, setTechnicalToolsOpen] = useState(false);

  const isBlocked = preview.summary.status === "blocked";
  const categories = preview.summary.categories;
  const localCategories = categories.filter((category) => !category.crosses_trust_boundary);
  const sentCategories = categories.filter((category) => category.crosses_trust_boundary);

  const showExportRestore = demoTransparencyEnabled && !isBlocked;
  const showVaultExplorer = demoVaultExplorerEnabled;
  const showTechnicalTools = showExportRestore || showVaultExplorer;

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
        <h2 className={styles.subheading}>{copy.review.willBeSentHeading}</h2>
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
      </div>

      {preview.inspection !== null && (
        <details
          className={styles.levelDisclosure}
          open={changesOpen}
          onToggle={(event) => setChangesOpen(event.currentTarget.open)}
        >
          <summary>{copy.review.understandChangesToggle}</summary>
          {changesOpen && (
            <DisclosureInspector
              inspection={preview.inspection}
              categories={preview.summary.categories}
              treatment={preview.treatment}
              strategy={preview.strategy}
            />
          )}
        </details>
      )}

      {showTechnicalTools && (
        <details
          className={styles.levelDisclosure}
          open={technicalToolsOpen}
          onToggle={(event) => setTechnicalToolsOpen(event.currentTarget.open)}
        >
          <summary>{copy.review.technicalToolsToggle}</summary>
          {technicalToolsOpen && (
            <div className={styles.technicalTools}>
              <p className={styles.explanation}>{copy.review.technicalToolsIntro}</p>
              {showExportRestore && <ExportRestorePanel compose={compose} />}
              {showVaultExplorer && <VaultExplorerPanel token={preview.vault_explorer_token} />}
            </div>
          )}
        </details>
      )}

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
