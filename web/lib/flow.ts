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
import type { PreviewResponse, ExecuteResponse } from "./contracts";
import type { DisplayError } from "./api";

export type EntryMode = "example" | "upload" | "paste";

/** `.txt`/`.md` only -- `docs/advisor-demo.md`'s supported upload path. */
export const SUPPORTED_UPLOAD_EXTENSIONS = [".txt", ".md"] as const;

export interface UploadedFile {
  filename: string;
  /** Full text content, read client-side via `FileReader.readAsText`. */
  content: string;
  byteSize: number;
  /** A simple, non-authoritative type label derived from the extension. */
  mimeGuess: string;
}

export interface ComposeState {
  mode: EntryMode;
  exampleId: string | null;
  pastedText: string;
  file: UploadedFile | null;
  /** Client-side validation/read error for the upload path (copy.ts text). */
  fileError: string | null;
  task: string;
}

export const initialComposeState: ComposeState = {
  mode: "example",
  exampleId: null,
  pastedText: "",
  file: null,
  fileError: null,
  task: "",
};

export type FlowState =
  | { screen: "welcome" }
  | { screen: "compose"; compose: ComposeState; submitError: DisplayError | null }
  | { screen: "previewing"; compose: ComposeState }
  | {
      screen: "review";
      compose: ComposeState;
      preview: PreviewResponse;
      executeError: DisplayError | null;
    }
  | { screen: "executing"; compose: ComposeState; preview: PreviewResponse }
  | {
      screen: "result";
      compose: ComposeState;
      preview: PreviewResponse;
      execute: ExecuteResponse;
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
  | { type: "SUBMIT_COMPOSE" }
  | { type: "PREVIEW_SUCCEEDED"; preview: PreviewResponse }
  | { type: "PREVIEW_FAILED"; error: DisplayError }
  | { type: "CONFIRM_REVIEW" }
  | { type: "CANCEL_REVIEW" }
  | { type: "EXECUTE_SUCCEEDED"; execute: ExecuteResponse }
  | { type: "EXECUTE_FAILED"; error: DisplayError }
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
    case "welcome":
    case "result":
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
      return { screen: "executing", compose: state.compose, preview: state.preview };
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
      };
    case "EXECUTE_FAILED":
      return {
        screen: "review",
        compose: state.compose,
        preview: state.preview,
        executeError: event.error,
      };
    default:
      return state;
  }
}

/**
 * Whether `filename` has a supported extension for the upload path. Client
 * side only -- an accepted name still goes through the same
 * `file_content`+`filename` JSON contract as any other input, never a
 * separate/invented multipart endpoint.
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
      return compose.file !== null;
    case "paste":
      return compose.pastedText.trim().length > 0;
  }
}

/**
 * Builds the exact `DisclosureRequestBody` for the current compose state.
 * Deliberately never sets `strategy` -- the API's "recommended" default is
 * used by omission (`docs/advisor-demo.md` / issue #29: the primary path
 * must never require knowing B0-B4), and never sets `governance` -- this
 * slice has no advanced/policy controls.
 */
export function buildRequestBody(compose: ComposeState): DisclosureRequestBody {
  const body: DisclosureRequestBody = {};

  if (compose.mode === "example" && compose.exampleId !== null) {
    body.example_id = compose.exampleId;
  } else if (compose.mode === "upload" && compose.file !== null) {
    body.file_content = compose.file.content;
    body.filename = compose.file.filename;
  } else if (compose.mode === "paste") {
    body.text = compose.pastedText;
  }

  const trimmedTask = compose.task.trim();
  if (trimmedTask.length > 0) {
    body.task = trimmedTask;
  }

  return body;
}
