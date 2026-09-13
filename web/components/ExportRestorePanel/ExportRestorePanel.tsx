"use client";

/**
 * T28 / issue #70 -- the export/restore demonstration panel. Rendered from
 * `ReviewScreen` only when the demo transparency feature flag is enabled
 * AND the preview is `allowed` (both checked by the caller, not here).
 *
 * Export is upload-only, mirroring T26's HTTP export route itself (its
 * upstream request takes the same multipart document shape as the preview
 * route -- no plain-text/example variant exists). In any other compose mode
 * this renders an explanatory note instead of the export button; restore
 * stays fully available regardless of mode, since it only needs a handle
 * and some text, neither tied to the current compose state.
 *
 * Every piece of state this component touches -- the export result, the
 * restore handle, the "simulated external response" text, the restore
 * result -- lives ONLY in this component's own `useState`. Nothing is
 * written to `localStorage`/`sessionStorage`/IndexedDB, the URL, or any
 * `console.*` call, and nothing survives past this component unmounting
 * (leaving the review screen, restarting the flow, cancelling): React
 * discards local state on unmount by construction, so there is no separate
 * "clear" step required for that path -- `handleClear` exists for the
 * user to reset the panel WITHOUT navigating away.
 *
 * The restore handle is rendered ONLY in a masked/truncated form
 * (`maskHandle` below) -- the full value is copyable/downloadable as an
 * explicit user action, never displayed verbatim, and never assembled into
 * any mapping-shaped structure alongside an original value: this panel
 * renders exactly two free-form strings (the exported `external_payload`
 * and the restored text), never a list/table pairing a pseudonym with what
 * it decodes to.
 */

import { useState } from "react";

import { useCopy } from "@/i18n/useLocale";
import { exportDocument, restoreText, type DisplayError } from "@/lib/api";
import type { ExportResponse, RestoreResponse } from "@/lib/contracts";
import { buildDocumentFormData, type ComposeState } from "@/lib/flow";

import styles from "./ExportRestorePanel.module.css";

export interface ExportRestorePanelProps {
  compose: ComposeState;
}

type ExportState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "succeeded"; data: ExportResponse }
  | { status: "failed"; error: DisplayError };

type RestoreState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "succeeded"; data: RestoreResponse }
  | { status: "failed"; error: DisplayError };

/** Shows only the first 6 and last 4 characters -- never the full handle. */
function maskHandle(handle: string): string {
  if (handle.length <= 12) {
    return `${handle.slice(0, 2)}…${handle.slice(-2)}`;
  }
  return `${handle.slice(0, 6)}…${handle.slice(-4)}`;
}

function formatExpiry(epochSeconds: number): string {
  const date = new Date(epochSeconds * 1000);
  return date.toLocaleString();
}

export function ExportRestorePanel({ compose }: ExportRestorePanelProps) {
  const copy = useCopy();
  const [exportState, setExportState] = useState<ExportState>({ status: "idle" });
  const [restoreState, setRestoreState] = useState<RestoreState>({ status: "idle" });
  const [handle, setHandle] = useState<string | null>(null);
  const [simulatedText, setSimulatedText] = useState("");
  const [copyFeedback, setCopyFeedback] = useState(false);

  const canExport = compose.mode === "upload";

  async function handleExport() {
    if (!canExport) {
      return;
    }
    setExportState({ status: "loading" });
    const form = buildDocumentFormData(compose);
    const result = await exportDocument(form, copy);
    if (result.ok) {
      setExportState({ status: "succeeded", data: result.data });
      setHandle(result.data.restore_handle);
      setSimulatedText(result.data.external_payload);
      setCopyFeedback(false);
    } else {
      setExportState({ status: "failed", error: result.error });
    }
  }

  async function handleRestore() {
    if (handle === null) {
      return;
    }
    setRestoreState({ status: "loading" });
    const result = await restoreText({ text: simulatedText, restore_handle: handle }, copy);
    if (result.ok) {
      setRestoreState({ status: "succeeded", data: result.data });
    } else {
      setRestoreState({ status: "failed", error: result.error });
    }
  }

  function handleClear() {
    setExportState({ status: "idle" });
    setRestoreState({ status: "idle" });
    setHandle(null);
    setSimulatedText("");
    setCopyFeedback(false);
  }

  async function handleCopyHandle() {
    if (handle === null) {
      return;
    }
    try {
      await navigator.clipboard.writeText(handle);
      setCopyFeedback(true);
    } catch {
      // Clipboard access can fail (permissions, insecure context, jsdom
      // without the API at all) -- this is a convenience action only, and
      // download/manual copy of the masked-but-selectable text stay
      // available regardless.
    }
  }

  function handleDownloadHandle() {
    if (handle === null) {
      return;
    }
    const blob = new Blob([handle], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "restore-handle.txt";
    link.click();
    URL.revokeObjectURL(url);
  }

  function handleImportHandle(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const text = typeof reader.result === "string" ? reader.result.trim() : "";
      if (text.length > 0) {
        setHandle(text);
      }
    };
    reader.readAsText(file);
  }

  const exportedData = exportState.status === "succeeded" ? exportState.data : null;

  return (
    <section className={styles.panel} aria-labelledby="export-restore-heading">
      <h2 id="export-restore-heading">{copy.exportRestorePanel.heading}</h2>
      <p className={styles.disclaimer}>{copy.exportRestorePanel.disclaimer}</p>

      {canExport ? (
        <button
          type="button"
          onClick={handleExport}
          disabled={exportState.status === "loading"}
        >
          {copy.exportRestorePanel.exportButton}
        </button>
      ) : (
        <p>{copy.exportRestorePanel.uploadOnlyNote}</p>
      )}

      {exportState.status === "failed" && (
        <p role="alert" className={styles.error}>
          {exportState.error.message}
        </p>
      )}

      {exportedData && (
        <div>
          <h3>{copy.exportRestorePanel.exportedPayloadHeading}</h3>
          <pre className={styles.pre} data-testid="export-payload">
            {exportedData.external_payload}
          </pre>
          <p data-testid="restorable-count">
            {exportedData.restorable_count} {copy.exportRestorePanel.restorableCountLabel}
          </p>
          <p>
            {copy.exportRestorePanel.expiresAtLabel} {formatExpiry(exportedData.expires_at)}
          </p>
          <p>
            {copy.exportRestorePanel.treatmentLabel} <code>{exportedData.treatment}</code>{" "}
            {copy.exportRestorePanel.strategyLabel} <code>{exportedData.strategy}</code>
          </p>
        </div>
      )}

      <div className={styles.handleBlock}>
        <h3>{copy.exportRestorePanel.handleHeading}</h3>
        <p>{copy.exportRestorePanel.handleHiddenNotice}</p>
        {handle !== null && <p className={styles.handleValue}>{maskHandle(handle)}</p>}
        <div className={styles.actionsRow}>
          <button type="button" onClick={handleCopyHandle} disabled={handle === null}>
            {copy.exportRestorePanel.copyHandleButton}
          </button>
          {copyFeedback && <span role="status">{copy.exportRestorePanel.copyHandleSuccess}</span>}
          <button type="button" onClick={handleDownloadHandle} disabled={handle === null}>
            {copy.exportRestorePanel.downloadHandleButton}
          </button>
        </div>
        <label>
          {copy.exportRestorePanel.importHandleLabel}
          <input type="file" accept=".txt,text/plain" onChange={handleImportHandle} />
        </label>
      </div>

      <div>
        <h3>{copy.exportRestorePanel.simulateResponseHeading}</h3>
        <p>{copy.exportRestorePanel.simulateResponseHint}</p>
        <textarea
          className={styles.textarea}
          value={simulatedText}
          onChange={(event) => setSimulatedText(event.target.value)}
          aria-label={copy.exportRestorePanel.simulateResponseHeading}
        />
        <div>
          <button
            type="button"
            onClick={handleRestore}
            disabled={handle === null || restoreState.status === "loading"}
          >
            {copy.exportRestorePanel.restoreButton}
          </button>
        </div>
      </div>

      {restoreState.status === "failed" && (
        <p role="alert" className={styles.error}>
          {restoreState.error.message}
        </p>
      )}

      {restoreState.status === "succeeded" && (
        <div>
          <h3>{copy.exportRestorePanel.restoredResultHeading}</h3>
          <pre className={styles.pre} data-testid="restored-text">
            {restoreState.data.restored_text}
          </pre>
          <p>
            {restoreState.data.restored_count} {copy.exportRestorePanel.restoredCountLabel}
          </p>
          <p>
            {restoreState.data.unresolved_count} {copy.exportRestorePanel.unresolvedCountLabel}
          </p>
          <p>{copy.exportRestorePanel.unresolvedExplanation}</p>
        </div>
      )}

      <button type="button" className={styles.clearButton} onClick={handleClear}>
        {copy.exportRestorePanel.clearButton}
      </button>
    </section>
  );
}
