/**
 * The guided flow's state machine (screens 1-4 of `docs/advisor-demo.md`'s
 * MVP v2 experience: Boas-vindas -> Novo teste -> Revisão -> Resultado).
 *
 * This module is deliberately framework-free: a pure reducer plus a couple
 * of pure helpers, so the flow's shape (which screen follows which event,
 * what data each screen carries) is testable without rendering anything.
 * `components/GuidedFlow` is the only caller -- it owns the `useReducer`
 * and the actual `lib/api` calls, then feeds their results back in as
 * `PREVIEW_SUCCEEDED` / `PREVIEW_FAILED` / `EXECUTE_SUCCEEDED` /
 * `EXECUTE_FAILED` events.
 *
 * The single most important property this reducer enforces structurally:
 * `EXECUTE_SUCCEEDED`/`EXECUTE_FAILED` only have an effect from the
 * "executing" screen, and the only way to reach "executing" is
 * `CONFIRM_REVIEW` fired from the "review" screen. There is no event that
 * jumps straight from "compose" or "previewing" to "executing" -- see
 * `flow.test.ts`'s "never calls execute before the user confirms on
 * review" tests.
 */

import type { DisclosureRequestBody } from "./contracts";
import type { CompareResponse, PreviewResponse, ExecuteResponse } from "./contracts";
import type { DisplayError } from "./api";

export type EntryMode = "example" | "upload" | "paste";

/** First-demo document formats; backend validation remains authoritative. */
export const SUPPORTED_UPLOAD_EXTENSIONS = [".pdf", ".docx", ".txt", ".md"] as const;

export interface UploadedFile {
  /** Original browser object retained only in memory for the confirmed re-upload. */
  file: File;
  filename: string;
  byteSize: number;
  /** Human-facing, non-authoritative type derived from the extension. */
  displayType: string;
}

export interface ComposeState {
  mode: EntryMode;
  exampleId: string | null;
  pastedText: string;
  file: UploadedFile | null;
  /** Client-side validation/read error for the upload path (copy.ts text). */
  fileError: string | null;
  task: string;
  documentType: string | null;
  analysisMode: string | null;
}

export const initialComposeState: ComposeState = {
  mode: "example",
  exampleId: null,
  pastedText: "",
  file: null,
  fileError: null,
  task: "",
  documentType: null,
  analysisMode: null,
};

export type FlowState =
  | { screen: "welcome" }
  | { screen: "compose"; compose: ComposeState; submitError: DisplayError | null }
  | { screen: "previewing"; compose: ComposeState }
  | {
      screen: "review";
      compose: ComposeState;
      preview: PreviewResponse;
      confirmationToken: string | null;
      executeError: DisplayError | null;
    }
  | { screen: "executing"; compose: ComposeState; preview: PreviewResponse; confirmationToken: string | null }
  | {
      screen: "result";
      compose: ComposeState;
      preview: PreviewResponse;
      execute: ExecuteResponse;
      /** Set by a failed comparison request; rendered inline on Result. */
      compareError: DisplayError | null;
    }
  | {
      screen: "technicalDetails";
      compose: ComposeState;
      preview: PreviewResponse;
      execute: ExecuteResponse;
      /**
       * Carried through unchanged from the Result screen the user opened
       * this from -- opening/closing "Ver detalhes técnicos" is pure
       * client-side navigation over the SAME `execute`/`preview` already in
       * state and must not touch a prior comparison error either way.
       */
      compareError: DisplayError | null;
    }
  | {
      screen: "comparing";
      compose: ComposeState;
      preview: PreviewResponse;
      execute: ExecuteResponse;
    }
  | {
      screen: "comparison";
      compose: ComposeState;
      preview: PreviewResponse;
      execute: ExecuteResponse;
      comparison: CompareResponse;
    };

export type FlowEvent =
  | { type: "START_TEST" }
  | { type: "SET_MODE"; mode: EntryMode }
  | { type: "SELECT_EXAMPLE"; exampleId: string }
  | { type: "SET_PASTED_TEXT"; text: string }
  | { type: "SET_FILE"; file: UploadedFile }
  | { type: "SET_FILE_ERROR"; message: string }
  | { type: "CLEAR_FILE" }
  | { type: "SET_TASK"; task: string }
  | { type: "SET_DOCUMENT_TYPE"; documentType: string; analysisMode: string }
  | { type: "SET_ANALYSIS_MODE"; analysisMode: string }
  | { type: "SUBMIT_COMPOSE" }
  | { type: "PREVIEW_SUCCEEDED"; preview: PreviewResponse; confirmationToken?: string }
  | { type: "PREVIEW_FAILED"; error: DisplayError }
  | { type: "CONFIRM_REVIEW" }
  | { type: "CANCEL_REVIEW" }
  | { type: "EXECUTE_SUCCEEDED"; execute: ExecuteResponse }
  | { type: "EXECUTE_FAILED"; error: DisplayError; requiresNewPreview?: boolean }
  | { type: "REQUEST_COMPARISON" }
  | { type: "COMPARE_SUCCEEDED"; comparison: CompareResponse }
  | { type: "COMPARE_FAILED"; error: DisplayError }
  | { type: "RETURN_TO_RESULT" }
  | { type: "OPEN_TECHNICAL_DETAILS" }
  | { type: "RESTART" };

export const initialFlowState: FlowState = { screen: "welcome" };

export function flowReducer(state: FlowState, event: FlowEvent): FlowState {
  // Global transitions available from any screen.
  if (event.type === "START_TEST" || event.type === "RESTART") {
    return { screen: "compose", compose: initialComposeState, submitError: null };
  }

  switch (state.screen) {
    case "compose":
      return composeReducer(state, event);
    case "previewing":
      return previewingReducer(state, event);
    case "review":
      return reviewReducer(state, event);
    case "executing":
      return executingReducer(state, event);
    case "result":
      return resultReducer(state, event);
    case "technicalDetails":
      return technicalDetailsReducer(state, event);
    case "comparing":
      return comparingReducer(state, event);
    case "comparison":
      return comparisonReducer(state, event);
    case "welcome":
      // No screen-specific event applies here besides the global ones
      // handled above -- unrecognized events are a no-op.
      return state;
  }
}

function composeReducer(
  state: Extract<FlowState, { screen: "compose" }>,
  event: FlowEvent,
): FlowState {
  switch (event.type) {
    case "SET_MODE":
      return { ...state, compose: { ...state.compose, mode: event.mode } };
    case "SELECT_EXAMPLE":
      return { ...state, compose: { ...state.compose, exampleId: event.exampleId } };
    case "SET_PASTED_TEXT":
      return { ...state, compose: { ...state.compose, pastedText: event.text } };
    case "SET_FILE":
      return {
        ...state,
        compose: { ...state.compose, file: event.file, fileError: null },
      };
    case "SET_FILE_ERROR":
      return {
        ...state,
        compose: { ...state.compose, file: null, fileError: event.message },
      };
    case "CLEAR_FILE":
      return { ...state, compose: { ...state.compose, file: null, fileError: null } };
    case "SET_TASK":
      return { ...state, compose: { ...state.compose, task: event.task } };
    case "SET_DOCUMENT_TYPE":
      return {
        ...state,
        compose: {
          ...state.compose,
          documentType: event.documentType,
          analysisMode: event.analysisMode,
        },
      };
    case "SET_ANALYSIS_MODE":
      return { ...state, compose: { ...state.compose, analysisMode: event.analysisMode } };
    case "SUBMIT_COMPOSE":
      return { screen: "previewing", compose: state.compose };
    default:
      return state;
  }
}

function previewingReducer(
  state: Extract<FlowState, { screen: "previewing" }>,
  event: FlowEvent,
): FlowState {
  switch (event.type) {
    case "PREVIEW_SUCCEEDED":
      return {
        screen: "review",
        compose: state.compose,
        preview: event.preview,
        confirmationToken: event.confirmationToken ?? null,
        executeError: null,
      };
    case "PREVIEW_FAILED":
      return { screen: "compose", compose: state.compose, submitError: event.error };
    default:
      return state;
  }
}

function reviewReducer(
  state: Extract<FlowState, { screen: "review" }>,
  event: FlowEvent,
): FlowState {
  switch (event.type) {
    case "CONFIRM_REVIEW":
      return {
        screen: "executing",
        compose: state.compose,
        preview: state.preview,
        confirmationToken: state.confirmationToken,
      };
    case "CANCEL_REVIEW":
      return { screen: "compose", compose: state.compose, submitError: null };
    default:
      return state;
  }
}

function executingReducer(
  state: Extract<FlowState, { screen: "executing" }>,
  event: FlowEvent,
): FlowState {
  switch (event.type) {
    case "EXECUTE_SUCCEEDED":
      return {
        screen: "result",
        compose: state.compose,
        preview: state.preview,
        execute: event.execute,
        compareError: null,
      };
    case "EXECUTE_FAILED":
      if (event.requiresNewPreview) {
        return { screen: "compose", compose: state.compose, submitError: event.error };
      }
      return {
        screen: "review",
        compose: state.compose,
        preview: state.preview,
        confirmationToken: state.confirmationToken,
        executeError: event.error,
      };
    default:
      return state;
  }
}

/**
 * The Result screen's screen-specific events: requesting the B0-B4
 * comparison, and opening "Ver detalhes técnicos". `REQUEST_COMPARISON` is
 * the ONLY event that reaches the "comparing" screen -- mirrors
 * `CONFIRM_REVIEW` being the only path to "executing" (see this module's
 * docstring) -- so a comparison can never be fetched as a side effect of any
 * other action on Result. `OPEN_TECHNICAL_DETAILS` is the ONLY event that
 * reaches "technicalDetails", and unlike the comparison path it triggers no
 * request at all: it carries the SAME `preview`/`execute`/`compareError`
 * already in state straight through, so opening the technical-details
 * screen can never call `/disclosure/preview`, `/disclosure/execute` or
 * `/disclosure/compare`.
 */
function resultReducer(
  state: Extract<FlowState, { screen: "result" }>,
  event: FlowEvent,
): FlowState {
  switch (event.type) {
    case "REQUEST_COMPARISON":
      return {
        screen: "comparing",
        compose: state.compose,
        preview: state.preview,
        execute: state.execute,
      };
    case "OPEN_TECHNICAL_DETAILS":
      return {
        screen: "technicalDetails",
        compose: state.compose,
        preview: state.preview,
        execute: state.execute,
        compareError: state.compareError,
      };
    default:
      return state;
  }
}

/**
 * `RETURN_TO_RESULT` is shared with the comparison screen (see
 * `comparisonReducer` below) rather than a second invented return event --
 * both screens go back to the SAME Result state over the SAME
 * `preview`/`execute` already held, never re-fetched. Unlike
 * `comparisonReducer`, `compareError` is threaded through UNCHANGED here:
 * nothing on the technical-details screen can affect or resolve a prior
 * failed comparison, so the Result screen the user returns to must be
 * byte-for-byte the one they left, error state included.
 */
function technicalDetailsReducer(
  state: Extract<FlowState, { screen: "technicalDetails" }>,
  event: FlowEvent,
): FlowState {
  switch (event.type) {
    case "RETURN_TO_RESULT":
      return {
        screen: "result",
        compose: state.compose,
        preview: state.preview,
        execute: state.execute,
        compareError: state.compareError,
      };
    default:
      return state;
  }
}

function comparingReducer(
  state: Extract<FlowState, { screen: "comparing" }>,
  event: FlowEvent,
): FlowState {
  switch (event.type) {
    case "COMPARE_SUCCEEDED":
      return {
        screen: "comparison",
        compose: state.compose,
        preview: state.preview,
        execute: state.execute,
        comparison: event.comparison,
      };
    case "COMPARE_FAILED":
      return {
        screen: "result",
        compose: state.compose,
        preview: state.preview,
        execute: state.execute,
        compareError: event.error,
      };
    default:
      return state;
  }
}

/**
 * `RETURN_TO_RESULT` is the only way back from the comparison screen (plus
 * the global `RESTART`) -- the original `execute`/`preview` the user already
 * saw are threaded straight through, never re-fetched or discarded, so the
 * Result screen the user returns to is the same one they left.
 */
function comparisonReducer(
  state: Extract<FlowState, { screen: "comparison" }>,
  event: FlowEvent,
): FlowState {
  switch (event.type) {
    case "RETURN_TO_RESULT":
      return {
        screen: "result",
        compose: state.compose,
        preview: state.preview,
        execute: state.execute,
        compareError: null,
      };
    default:
      return state;
  }
}

/**
 * Whether `filename` has a supported extension for the upload path. Client
 * side only -- accepted files still go through the backend's multipart
 * ingestion boundary, which remains authoritative.
 */
export function isSupportedUploadFilename(filename: string): boolean {
  const lower = filename.toLowerCase();
  return SUPPORTED_UPLOAD_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

/** Whether `compose` currently has enough information to submit for preview. */
export function isComposeReady(compose: ComposeState): boolean {
  switch (compose.mode) {
    case "example":
      return compose.exampleId !== null;
    case "upload":
      return (
        compose.file !== null &&
        compose.documentType !== null &&
        compose.analysisMode !== null &&
        compose.task.trim().length > 0
      );
    case "paste":
      return compose.pastedText.trim().length > 0;
  }
}

/**
 * Builds the exact historical JSON request for example and paste modes.
 * Deliberately never sets `strategy` -- the API's "recommended" default is
 * used by omission (`docs/advisor-demo.md` / issue #29: the primary path
 * must never require knowing B0-B4), and never sets `governance` -- this
 * slice has no advanced/policy controls.
 */
export function buildRequestBody(compose: ComposeState): DisclosureRequestBody {
  const body: DisclosureRequestBody = {};

  if (compose.mode === "example" && compose.exampleId !== null) {
    body.example_id = compose.exampleId;
  } else if (compose.mode === "paste") {
    body.text = compose.pastedText;
  }

  const trimmedTask = compose.task.trim();
  if (trimmedTask.length > 0) {
    body.task = trimmedTask;
  }

  return body;
}

/** Build the explicit multipart contract for the structured document routes. */
export function buildDocumentFormData(
  compose: ComposeState,
  confirmationToken?: string,
): FormData {
  if (
    compose.mode !== "upload" ||
    compose.file === null ||
    compose.documentType === null ||
    compose.analysisMode === null
  ) {
    throw new Error("document upload state is incomplete");
  }

  const form = new FormData();
  form.append("file", compose.file.file);
  form.append("task", compose.task.trim());
  form.append("document_type", compose.documentType);
  form.append("analysis_mode", compose.analysisMode);
  if (confirmationToken !== undefined) {
    form.append("confirmation_token", confirmationToken);
  }
  return form;
}
