"use client";

/**
 * Screen 2 -- "Novo teste" (`docs/advisor-demo.md`). Three entry modes
 * (example / upload / paste) plus a natural-language task field.
 *
 * The primary path must never require knowing B0-B4 (issue #29): there is
 * no treatment/strategy/policy/provider selector anywhere on this screen,
 * and `buildRequestBody` (`lib/flow.ts`) never sends a `strategy` field, so
 * the API's "recommended" default applies by omission.
 *
 * Upload retains the original `File` object in memory and never decodes it
 * in the browser. `GuidedFlow` sends it as multipart data to the structured
 * document preview endpoint, then reuses the same object for the explicitly
 * confirmed execute request. PDF/DOCX therefore never pass through
 * `FileReader.readAsText`; TXT/MD deliberately use the same single upload
 * path. The backend remains authoritative for size and format validation.
 */

import { useRef, type ChangeEvent, type DragEvent, type FormEvent } from "react";

import { useCopy } from "@/i18n/useLocale";
import type { DisplayError } from "@/lib/api";
import type { DocumentType, ExampleSummary } from "@/lib/contracts";
import { describeExample } from "@/lib/exampleLabels";
import {
  isComposeReady,
  isSupportedUploadFilename,
  type ComposeState,
  type EntryMode,
  type FlowEvent,
  type UploadedFile,
} from "@/lib/flow";

import styles from "./ComposeScreen.module.css";

export interface ComposeScreenProps {
  compose: ComposeState;
  submitError: DisplayError | null;
  examples: ExampleSummary[] | null;
  examplesError: DisplayError | null;
  documentTypes: DocumentType[] | null;
  documentTypesError: DisplayError | null;
  dispatch: (event: FlowEvent) => void;
  onSubmit: () => void;
}

function formatByteSize(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  return `${(bytes / 1024).toFixed(1)} KB`;
}

function extensionFor(filename: string): string {
  return filename.split(".").pop()?.toLowerCase() ?? "";
}

export function ComposeScreen({
  compose,
  submitError,
  examples,
  examplesError,
  documentTypes,
  documentTypesError,
  dispatch,
  onSubmit,
}: ComposeScreenProps) {
  const copy = useCopy();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const selectedExample = examples?.find(
    (example) => example.example_id === compose.exampleId,
  );

  function selectFile(file: File) {
    if (!isSupportedUploadFilename(file.name)) {
      dispatch({ type: "SET_FILE_ERROR", message: copy.newTest.uploadUnsupportedType });
      return;
    }

    const extension = extensionFor(file.name);
    const uploaded: UploadedFile = {
      file,
      filename: file.name,
      byteSize: file.size,
      displayType: copy.newTest.fileTypeLabels[extension] ?? extension.toUpperCase(),
    };
    dispatch({ type: "SET_FILE", file: uploaded });
  }

  function handleFileInputChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (file) {
      selectFile(file);
    }
    // Reset so choosing the same filename again still fires onChange.
    event.target.value = "";
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    const file = event.dataTransfer.files?.[0];
    if (file) {
      selectFile(file);
    }
  }

  function handleDragOver(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!isComposeReady(compose)) {
      return;
    }
    onSubmit();
  }

  return (
    <form className={styles.form} onSubmit={handleSubmit}>
      <h1 className={styles.heading}>{copy.newTest.heading}</h1>

      <fieldset className={styles.fieldset}>
        <legend className={styles.legend}>{copy.entryModes.heading}</legend>

        <label className={styles.modeOption}>
          <input
            type="radio"
            name="entry-mode"
            value="example"
            checked={compose.mode === "example"}
            onChange={() => dispatch({ type: "SET_MODE", mode: "example" as EntryMode })}
          />
          {copy.entryModes.useExample}
        </label>

        <label className={styles.modeOption}>
          <input
            type="radio"
            name="entry-mode"
            value="upload"
            checked={compose.mode === "upload"}
            onChange={() => dispatch({ type: "SET_MODE", mode: "upload" as EntryMode })}
          />
          {copy.entryModes.uploadFile}
        </label>

        <label className={styles.modeOption}>
          <input
            type="radio"
            name="entry-mode"
            value="paste"
            checked={compose.mode === "paste"}
            onChange={() => dispatch({ type: "SET_MODE", mode: "paste" as EntryMode })}
          />
          {copy.entryModes.pasteText}
        </label>
      </fieldset>

      {compose.mode === "example" && (
        <div className={styles.field}>
          <label className={styles.label} htmlFor="example-select">
            {copy.newTest.exampleFieldLabel}
          </label>
          {examplesError ? (
            <p className={styles.error}>{copy.newTest.exampleLoadError}</p>
          ) : examples === null ? (
            <p role="status" aria-live="polite">
              {copy.newTest.exampleLoading}
            </p>
          ) : (
            <select
              id="example-select"
              className={styles.select}
              value={compose.exampleId ?? ""}
              onChange={(event) =>
                dispatch({ type: "SELECT_EXAMPLE", exampleId: event.target.value })
              }
            >
              <option value="" disabled>
                {copy.newTest.examplePlaceholder}
              </option>
              {examples.map((example) => (
                <option key={example.example_id} value={example.example_id}>
                  {describeExample(example, examples, copy).label}
                </option>
              ))}
            </select>
          )}
          {/*
            Progressive disclosure: the reviewer picks by plain-language
            purpose above, and the raw corpus sample id stays available
            underneath as a technical detail -- never as the primary label.
            See lib/exampleLabels.ts.
          */}
          {selectedExample !== undefined && (
            <p className={styles.hint}>
              {copy.newTest.exampleTechnicalIdLabel}{" "}
              <code>{describeExample(selectedExample, examples ?? [], copy).technicalId}</code>
            </p>
          )}
        </div>
      )}

      {compose.mode === "upload" && (
        <div className={styles.field}>
          <div
            className={styles.dropzone}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
          >
            <label className={styles.label} htmlFor="file-input">
              {copy.newTest.uploadFieldLabel}
            </label>
            <input
              id="file-input"
              ref={fileInputRef}
              type="file"
              accept=".pdf,.docx,.txt,.md"
              onChange={handleFileInputChange}
            />
            <p className={styles.hint}>{copy.newTest.uploadDropHint}</p>
          </div>

          {compose.fileError && <p className={styles.error}>{compose.fileError}</p>}

          {compose.file && (
            <div>
              <dl className={styles.fileDetails}>
                <dt className={styles.fileDetailsTerm}>{copy.newTest.fileNameLabel}</dt>
                <dd>{compose.file.filename}</dd>
                <dt className={styles.fileDetailsTerm}>{copy.newTest.fileTypeLabel}</dt>
                <dd>{compose.file.displayType}</dd>
                <dt className={styles.fileDetailsTerm}>{copy.newTest.fileSizeLabel}</dt>
                <dd>{formatByteSize(compose.file.byteSize)}</dd>
              </dl>
              <button
                type="button"
                className={styles.removeFileButton}
                onClick={() => dispatch({ type: "CLEAR_FILE" })}
              >
                {copy.newTest.removeFile}
              </button>
            </div>
          )}

          <label className={styles.label} htmlFor="document-type">
            {copy.newTest.documentTypeLabel}
          </label>
          {documentTypesError ? (
            <p className={styles.error}>{copy.newTest.documentTypesLoadError}</p>
          ) : documentTypes === null ? (
            <p role="status">{copy.newTest.documentTypesLoading}</p>
          ) : (
            <select
              id="document-type"
              className={styles.select}
              value={compose.documentType ?? ""}
              onChange={(event) => {
                const selected = documentTypes.find(
                  (item) => item.document_type === event.target.value,
                );
                if (selected) {
                  dispatch({
                    type: "SET_DOCUMENT_TYPE",
                    documentType: selected.document_type,
                    analysisMode: selected.default_analysis_mode,
                  });
                }
              }}
            >
              {documentTypes.map((item) => (
                <option key={item.document_type} value={item.document_type}>
                  {copy.newTest.documentTypeLabels[item.document_type] ?? item.document_type}
                </option>
              ))}
            </select>
          )}

          {compose.documentType && documentTypes && (
            <>
              <label className={styles.label} htmlFor="analysis-mode">
                {copy.newTest.analysisModeLabel}
              </label>
              <select
                id="analysis-mode"
                className={styles.select}
                value={compose.analysisMode ?? ""}
                onChange={(event) =>
                  dispatch({ type: "SET_ANALYSIS_MODE", analysisMode: event.target.value })
                }
              >
                {documentTypes
                  .find((item) => item.document_type === compose.documentType)
                  ?.analysis_modes.map((mode) => (
                    <option key={mode} value={mode}>
                      {copy.newTest.analysisModeLabels[mode] ?? mode}
                    </option>
                  ))}
              </select>
            </>
          )}
        </div>
      )}

      {compose.mode === "paste" && (
        <div className={styles.field}>
          <label className={styles.label} htmlFor="paste-text">
            {copy.newTest.pasteLabel}
          </label>
          <textarea
            id="paste-text"
            className={styles.textarea}
            placeholder={copy.newTest.pastePlaceholder}
            value={compose.pastedText}
            onChange={(event) => dispatch({ type: "SET_PASTED_TEXT", text: event.target.value })}
          />
        </div>
      )}

      <div className={styles.field}>
        <label className={styles.label} htmlFor="task-field">
          {copy.newTest.taskLabel}
        </label>
        <textarea
          id="task-field"
          className={styles.textarea}
          placeholder={copy.newTest.taskPlaceholder}
          value={compose.task}
          onChange={(event) => dispatch({ type: "SET_TASK", task: event.target.value })}
        />
        {compose.mode === "example" && <p className={styles.hint}>{copy.newTest.taskHintForExample}</p>}
      </div>

      {submitError && (
        <p role="alert" className={styles.error}>
          {submitError.message}
        </p>
      )}

      {!isComposeReady(compose) && <p className={styles.hint}>{copy.newTest.incompleteHint}</p>}

      <button type="submit" className={styles.submitButton} disabled={!isComposeReady(compose)}>
        {copy.newTest.continueToReview}
      </button>
    </form>
  );
}
