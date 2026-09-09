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
 * Upload reads the file client-side via `FileReader.readAsText` and stores
 * its text content in compose state; `lib/flow.ts`'s `buildRequestBody`
 * later sends that as `file_content` + `filename` -- the exact JSON shape
 * `POST /disclosure/preview` accepts. Extension validation
 * (`isSupportedUploadFilename`) happens BEFORE any read, so an unsupported
 * file never reaches `FileReader` and never reaches the API client.
 *
 * --- KNOWN GAP: there is no upload size limit anywhere in this path ---
 *
 * `readAsText` buffers the entire file in memory, `buildRequestBody`
 * inlines the whole string into a JSON body, and neither the Next route
 * handler (`app/api/disclosure/preview`, which streams the body through
 * `request.text()`) nor the Python API (no body-size ceiling in
 * `api/app.py` or in uvicorn's defaults) bounds it. A large enough .txt is
 * therefore a browser-tab memory problem and an unbounded upstream request.
 *
 * This is deliberately NOT fixed in this slice, for two reasons rather than
 * for convenience:
 *
 *  1. A cap enforced only here would not be a control. The API accepts the
 *     identical JSON from `curl`, so a client-side check is a usability
 *     affordance, not a limit -- the enforceable boundary is where the
 *     request is ACCEPTED (reverse proxy / uvicorn / ASGI middleware),
 *     which is T25's deployment surface, and secondarily at ingestion,
 *     which is T12's.
 *  2. Choosing the number is a real decision, not a detail. The ceiling
 *     bounds which documents the demo will accept at all, and it has to be
 *     reconciled with the corpus's own sizes and with T12's Docling
 *     ingestion path. Inventing one here would freeze an arbitrary
 *     methodological constraint inside a UI component.
 *
 * Tracked as a follow-up on T25 (#42, enforcement point) and T12 (#9,
 * ingestion limits). See this PR's description.
 */

import { useRef, useState, type ChangeEvent, type DragEvent, type FormEvent } from "react";

import type { DisplayError } from "@/lib/api";
import type { ExampleSummary } from "@/lib/contracts";
import { copy } from "@/lib/copy";
import { describeExample } from "@/lib/exampleLabels";
import {
  isComposeReady,
  isSupportedUploadFilename,
  type ComposeState,
  type EntryMode,
  type FlowEvent,
  type UploadedFile,
} from "@/lib/flow";

import { ProcessingStatus } from "../ProcessingStatus/ProcessingStatus";
import styles from "./ComposeScreen.module.css";

export interface ComposeScreenProps {
  compose: ComposeState;
  submitError: DisplayError | null;
  examples: ExampleSummary[] | null;
  examplesError: DisplayError | null;
  dispatch: (event: FlowEvent) => void;
  onSubmit: () => void;
}

function formatByteSize(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  return `${(bytes / 1024).toFixed(1)} KB`;
}

function mimeGuessFor(filename: string): string {
  return filename.toLowerCase().endsWith(".md") ? "text/markdown" : "text/plain";
}

export function ComposeScreen({
  compose,
  submitError,
  examples,
  examplesError,
  dispatch,
  onSubmit,
}: ComposeScreenProps) {
  const [isReadingFile, setIsReadingFile] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const selectedExample = examples?.find(
    (example) => example.example_id === compose.exampleId,
  );

  function readFile(file: File) {
    if (!isSupportedUploadFilename(file.name)) {
      dispatch({ type: "SET_FILE_ERROR", message: copy.newTest.uploadUnsupportedType });
      return;
    }

    setIsReadingFile(true);
    const reader = new FileReader();
    reader.onload = () => {
      const content = typeof reader.result === "string" ? reader.result : "";
      const uploaded: UploadedFile = {
        filename: file.name,
        content,
        byteSize: file.size,
        mimeGuess: mimeGuessFor(file.name),
      };
      setIsReadingFile(false);
      dispatch({ type: "SET_FILE", file: uploaded });
    };
    reader.onerror = () => {
      setIsReadingFile(false);
      dispatch({ type: "SET_FILE_ERROR", message: copy.newTest.uploadReadError });
    };
    reader.readAsText(file);
  }

  function handleFileInputChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (file) {
      readFile(file);
    }
    // Reset so choosing the same filename again still fires onChange.
    event.target.value = "";
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    const file = event.dataTransfer.files?.[0];
    if (file) {
      readFile(file);
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
                  {describeExample(example, examples).label}
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
              <code>{describeExample(selectedExample, examples ?? []).technicalId}</code>
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
              accept=".txt,.md"
              onChange={handleFileInputChange}
            />
            <p className={styles.hint}>{copy.newTest.uploadDropHint}</p>
          </div>

          {isReadingFile && <ProcessingStatus stages={[copy.processingStages.readingFile]} />}

          {compose.fileError && <p className={styles.error}>{compose.fileError}</p>}

          {compose.file && (
            <div>
              <dl className={styles.fileDetails}>
                <dt className={styles.fileDetailsTerm}>{copy.newTest.fileNameLabel}</dt>
                <dd>{compose.file.filename}</dd>
                <dt className={styles.fileDetailsTerm}>{copy.newTest.fileTypeLabel}</dt>
                <dd>{compose.file.mimeGuess}</dd>
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
