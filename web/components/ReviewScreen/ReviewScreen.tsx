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
 *    -- prominently, under `copy.review.willBeSentHeading` -- what the
 *    gateway computed for this preview as the boundary-crossing categories,
 *    including the payload disclosure (still kept OUT of the DOM until its
 *    own toggle is opened, unchanged). This heading is forward-looking
 *    ("será enviado") and, for upload, is confirmation-bound to what
 *    `execute_document` actually sends; for paste/example, `executeDisclosure`
 *    recomputes the decision independently at confirm time (#103 review, PR
 *    #108), so this section shows what THIS preview computed, not a
 *    byte-identity guarantee with the later call.
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
 *
 * T32.2 / issue #102 made this a true check-before-send, in this order:
 * heading -> "What you asked for" (`ReviewContextSummary`, re-presenting the
 * retained compose context, with the single "Change" action) -> the Level-1
 * `DisclosureOverview` -> Levels 2/3 -> the plain-language consequence of
 * confirming -> the CTA. "Change" calls `onEdit`, which GuidedFlow wires to
 * `window.history.back()` -- the same history traversal as the shell's Back
 * button, back to the retained Compose snapshot -- never a parallel reducer
 * transition. The post-send, read-only counterpart is `ApprovedReviewScreen`,
 * a different component over a different (token-free) flow state.
 *
 * T32.3 / issue #103 adds the PRIMARY before/after right after "What you
 * asked for": `DisclosureTransformationSummary`, visible by default, built
 * only from `preview.inspection`. Both it and the Level-2 inspector render
 * only when `demoInspectionEnabled` (the INSPECTION capability, fetched by
 * GuidedFlow; any fetch failure is already `false`) AND
 * `preview.inspection !== null` agree -- neither the transparency nor the
 * vault flag ever implies it. Final order: heading -> "What you asked for"
 * -> "What the gateway did" -> detected / stays local / will be sent ->
 * Level 2 (detailed explanation) -> Level 3 (technical tools) -> consequence
 * -> Confirm.
 */

import { useState } from "react";

import { useCopy } from "@/i18n/useLocale";
import type { DisplayError } from "@/lib/api";
import type { ExampleSummary, PreviewResponse } from "@/lib/contracts";
import { initialComposeState, type ComposeState } from "@/lib/flow";

import { DisclosureInspector } from "../DisclosureInspector/DisclosureInspector";
import { DisclosureTransformationSummary } from "../DisclosureTransformationSummary/DisclosureTransformationSummary";
import { ExportRestorePanel } from "../ExportRestorePanel/ExportRestorePanel";
import { VaultExplorerPanel } from "../VaultExplorerPanel/VaultExplorerPanel";
import { DisclosureOverview } from "./DisclosureOverview";
import { ReviewContextSummary } from "./ReviewContextSummary";
import styles from "./ReviewScreen.module.css";

export interface ReviewScreenProps {
  preview: PreviewResponse;
  executeError: DisplayError | null;
  onConfirm: () => void;
  /** T32.2 / #102: the "Change" action -- GuidedFlow wires it to browser history Back. */
  onEdit: () => void;
  /**
   * The compose state this preview was built from -- rendered as the "What
   * you asked for" context (T32.2 / #102) and threaded through to
   * `ExportRestorePanel`. Optional, defaulting to the initial (example mode)
   * compose state, so existing callers/tests keep working.
   */
  compose?: ComposeState;
  /** The examples catalog, used only to give an example its human label. */
  examples?: readonly ExampleSummary[] | null;
  /**
   * T32.3 / issue #103. The INSPECTION capability (`demo_inspection_enabled`
   * from `getDemoFeatures`). Defaults to `false`: with it off, neither the
   * before/after nor the detailed inspector renders, even if the body
   * carries an inspection.
   */
  demoInspectionEnabled?: boolean;
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
  onEdit,
  compose = initialComposeState,
  examples = null,
  demoInspectionEnabled = false,
  demoTransparencyEnabled = false,
  demoVaultExplorerEnabled = false,
}: ReviewScreenProps) {
  const copy = useCopy();
  const [changesOpen, setChangesOpen] = useState(false);
  const [technicalToolsOpen, setTechnicalToolsOpen] = useState(false);

  const isBlocked = preview.summary.status === "blocked";
  const inspection = demoInspectionEnabled ? preview.inspection : null;

  const showExportRestore = demoTransparencyEnabled && !isBlocked;
  const showVaultExplorer = demoVaultExplorerEnabled;
  const showTechnicalTools = showExportRestore || showVaultExplorer;

  return (
    <section aria-labelledby="review-heading" className={styles.section}>
      <h1 id="review-heading" className={styles.heading}>
        {copy.review.heading}
      </h1>

      <ReviewContextSummary
        compose={compose}
        examples={examples}
        action={
          <button type="button" className={styles.cancelButton} onClick={onEdit}>
            {copy.review.changeRequest}
          </button>
        }
      />

      {inspection !== null && <DisclosureTransformationSummary inspection={inspection} variant="review" />}

      <DisclosureOverview
        preview={preview}
        sentHeading={copy.review.willBeSentHeading}
        payloadToggleLabel={copy.review.showPayloadToggle}
      />

      {inspection !== null && (
        <details
          className={styles.levelDisclosure}
          open={changesOpen}
          onToggle={(event) => setChangesOpen(event.currentTarget.open)}
        >
          <summary>{copy.review.understandChangesToggle}</summary>
          {changesOpen && (
            <DisclosureInspector
              inspection={inspection}
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
        <div>
          <p role="alert" className={styles.error}>
            {executeError.message}
          </p>
          <p className={styles.explanation}>{copy.review.executeErrorNoAutoRetry}</p>
        </div>
      )}

      {!isBlocked && (
        <div className={styles.decision}>
          <p>{copy.review.confirmConsequence}</p>
          <p className={styles.explanation}>{copy.review.afterSendNotice}</p>
          <div className={styles.actions}>
            <button type="button" className={styles.confirmButton} onClick={onConfirm}>
              {copy.review.confirmSend}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
