import { describe, expect, it } from "vitest";

import type { DisplayError } from "./api";
import type { CompareResponse, ExecuteResponse, PreviewResponse } from "./contracts";
import {
  approveReview,
  buildRequestBody,
  flowReducer,
  initialComposeState,
  initialFlowState,
  isComposeReady,
  isSupportedUploadFilename,
  type ComposeState,
  type FlowEvent,
  type FlowState,
} from "./flow";

const genericError: DisplayError = { message: "erro genérico", kind: null, fields: null };

function preview(overrides: Partial<PreviewResponse> = {}): PreviewResponse {
  return {
    contract_version: "t20-application-api-v1",
    summary: {
      status: "allowed",
      categories: [],
      detected_span_count: 0,
      detected_categories: [],
    },
    external_payload: "hello",
    payload_byte_count: 5,
    treatment: "b4",
    strategy: "recommended",
    governance: {
      domain: "demo",
      purpose: "demo",
      policy_version: "v1",
      provider_class: "FakeProvider",
      requester_role: null,
      requested_pseudonym_scope: "session",
    },
    provider_mode: { provider_class: "FakeProvider" },
    inspection: null,
    vault_explorer_token: null,
    ...overrides,
  };
}

function execute(overrides: Partial<ExecuteResponse> = {}): ExecuteResponse {
  return {
    contract_version: "t20-application-api-v1",
    status: "allowed",
    summary: {
      status: "allowed",
      categories: [],
      detected_span_count: 0,
      detected_categories: [],
    },
    final_answer: "resposta final",
    provider: {
      called: true,
      provider_class: "FakeProvider",
      model_id: "fake-1",
      model_snapshot: "2026-01-01",
      decoding_config: null,
      transmitted_bytes: 10,
      response_hash: "abc",
      failed: false,
      failure_kind: null,
    },
    reconstruction: {
      attempted: true,
      reconstructed_hash: "def",
      changed_from_provider_response: false,
    },
    treatment: "b4",
    strategy: "recommended",
    governance: {
      domain: "demo",
      purpose: "demo",
      policy_version: "v1",
      provider_class: "FakeProvider",
      requester_role: null,
      requested_pseudonym_scope: "session",
    },
    total_ms: 42,
    ...overrides,
  };
}

describe("flowReducer -- welcome and startup", () => {
  it("starts at the welcome screen", () => {
    expect(initialFlowState).toEqual({ screen: "welcome" });
  });

  it("START_TEST moves to compose with a fresh compose state", () => {
    const next = flowReducer(initialFlowState, { type: "START_TEST" });
    expect(next).toEqual({ screen: "compose", compose: initialComposeState, submitError: null });
  });
});

describe("flowReducer -- compose screen", () => {
  const composeState: FlowState = { screen: "compose", compose: initialComposeState, submitError: null };

  it("SET_MODE updates only the mode field", () => {
    const next = flowReducer(composeState, { type: "SET_MODE", mode: "paste" });
    expect(next).toMatchObject({ screen: "compose", compose: { mode: "paste" } });
  });

  it("SELECT_EXAMPLE records the chosen example id", () => {
    const next = flowReducer(composeState, { type: "SELECT_EXAMPLE", exampleId: "ex-1" });
    expect(next).toMatchObject({ compose: { exampleId: "ex-1" } });
  });

  it("SET_FILE clears any prior fileError", () => {
    const withError: FlowState = {
      screen: "compose",
      compose: { ...initialComposeState, fileError: "bad file" },
      submitError: null,
    };
    const raw = new File(["hi"], "doc.txt");
    const file = { file: raw, filename: "doc.txt", byteSize: 2, displayType: "Texto simples" };
    const next = flowReducer(withError, { type: "SET_FILE", file });
    expect(next).toMatchObject({ compose: { file, fileError: null } });
  });

  it("SET_FILE_ERROR clears any prior file", () => {
    const raw = new File(["hi"], "doc.txt");
    const file = { file: raw, filename: "doc.txt", byteSize: 2, displayType: "Texto simples" };
    const withFile: FlowState = {
      screen: "compose",
      compose: { ...initialComposeState, file },
      submitError: null,
    };
    const next = flowReducer(withFile, { type: "SET_FILE_ERROR", message: "unsupported" });
    expect(next).toMatchObject({ compose: { file: null, fileError: "unsupported" } });
  });

  it("SUBMIT_COMPOSE moves to previewing, carrying the compose state forward", () => {
    const compose: ComposeState = { ...initialComposeState, mode: "paste", pastedText: "content" };
    const state: FlowState = { screen: "compose", compose, submitError: null };
    const next = flowReducer(state, { type: "SUBMIT_COMPOSE" });
    expect(next).toEqual({ screen: "previewing", compose });
  });

  it("ignores CONFIRM_REVIEW and EXECUTE_* events -- there is no shortcut to executing", () => {
    expect(flowReducer(composeState, { type: "CONFIRM_REVIEW" })).toBe(composeState);
    expect(
      flowReducer(composeState, { type: "EXECUTE_SUCCEEDED", execute: execute() }),
    ).toBe(composeState);
  });
});

describe("flowReducer -- previewing screen", () => {
  const state: FlowState = { screen: "previewing", compose: initialComposeState };

  it("PREVIEW_SUCCEEDED moves to review carrying the preview payload", () => {
    const p = preview();
    const next = flowReducer(state, { type: "PREVIEW_SUCCEEDED", preview: p });
    expect(next).toEqual({
      screen: "review",
      compose: initialComposeState,
      preview: p,
      confirmationToken: null,
      executeError: null,
    });
  });

  it("PREVIEW_FAILED returns to compose with the error attached", () => {
    const next = flowReducer(state, { type: "PREVIEW_FAILED", error: genericError });
    expect(next).toEqual({
      screen: "compose",
      compose: initialComposeState,
      submitError: genericError,
    });
  });

  it("does not call/represent execute on any event here", () => {
    const next = flowReducer(state, { type: "CONFIRM_REVIEW" });
    expect(next).toBe(state);
  });
});

describe("flowReducer -- review screen (the confirm gate)", () => {
  const p = preview();
  const state: FlowState = {
    screen: "review",
    compose: initialComposeState,
    preview: p,
    confirmationToken: null,
    executeError: null,
  };

  it("CONFIRM_REVIEW is the ONLY event that reaches the executing screen", () => {
    const next = flowReducer(state, { type: "CONFIRM_REVIEW" });
    expect(next).toEqual({ screen: "executing", compose: initialComposeState, preview: p, confirmationToken: null });
  });

  it("CANCEL_REVIEW returns to compose, preserving the compose state, clearing errors", () => {
    const compose: ComposeState = { ...initialComposeState, task: "resuma" };
    const withTask: FlowState = { screen: "review", compose, preview: p, confirmationToken: null, executeError: null };
    const next = flowReducer(withTask, { type: "CANCEL_REVIEW" });
    expect(next).toEqual({ screen: "compose", compose, submitError: null });
  });

  it("EXECUTE_SUCCEEDED/EXECUTE_FAILED from review itself are no-ops (must come via executing)", () => {
    expect(flowReducer(state, { type: "EXECUTE_SUCCEEDED", execute: execute() })).toBe(state);
    expect(flowReducer(state, { type: "EXECUTE_FAILED", error: genericError })).toBe(state);
  });
});

describe("flowReducer -- executing screen", () => {
  const p = preview();
  const state: FlowState = { screen: "executing", compose: initialComposeState, preview: p, confirmationToken: null };

  it("EXECUTE_SUCCEEDED moves to result carrying the execute payload", () => {
    const e = execute();
    const next = flowReducer(state, { type: "EXECUTE_SUCCEEDED", execute: e });
    expect(next).toEqual({
      screen: "result",
      compose: initialComposeState,
      preview: p,
      execute: e,
      compareError: null,
    });
  });

  it("EXECUTE_FAILED returns to review (not compose, not a crash) with the error attached", () => {
    const next = flowReducer(state, { type: "EXECUTE_FAILED", error: genericError });
    expect(next).toEqual({
      screen: "review",
      compose: initialComposeState,
      preview: p,
      confirmationToken: null,
      executeError: genericError,
    });
  });

  it("an invalid preview confirmation returns to compose and requires a fresh preview", () => {
    const confirmationError: DisplayError = {
      message: "faça uma nova revisão",
      kind: "PreviewConfirmationError",
      fields: null,
    };
    const next = flowReducer(state, {
      type: "EXECUTE_FAILED",
      error: confirmationError,
      requiresNewPreview: true,
    });

    expect(next).toEqual({
      screen: "compose",
      compose: initialComposeState,
      submitError: confirmationError,
    });
  });
});

/**
 * T32.2 / #102: the Approved Review is the post-send, read-only historical
 * view of the Review a successful execute came from. It is a DISTINCT state
 * kind, not a flag on "review": the reducer must make it structurally
 * impossible to leave it for "executing", and the state must not carry a
 * confirmation token at all. Each assertion here fails from a real defect --
 * e.g. routing "approvedReview" through reviewReducer, or spreading the
 * review (token included) into the approved snapshot.
 */
describe("flowReducer -- approvedReview (post-send, read-only)", () => {
  const p = preview();
  const compose: ComposeState = { ...initialComposeState, mode: "paste", pastedText: "texto", task: "resuma" };
  const review: Extract<FlowState, { screen: "review" }> = {
    screen: "review",
    compose,
    preview: p,
    confirmationToken: "opaque.token",
    executeError: genericError,
  };

  it("approveReview keeps the reviewed context and preview but drops the token and any error", () => {
    const approved = approveReview(review);
    expect(approved).toEqual({ screen: "approvedReview", compose, preview: p });
    expect("confirmationToken" in approved).toBe(false);
    expect(JSON.stringify(approved)).not.toContain("opaque.token");
  });

  it("CONFIRM_REVIEW from approvedReview is a no-op -- it can never reach executing", () => {
    const approved = approveReview(review);
    expect(flowReducer(approved, { type: "CONFIRM_REVIEW" })).toBe(approved);
  });

  it("no screen-specific event leads from approvedReview anywhere (no resend, no edit, no compare)", () => {
    const approved = approveReview(review);
    const events: FlowEvent[] = [
      { type: "CONFIRM_REVIEW" },
      { type: "CANCEL_REVIEW" },
      { type: "EXECUTE_SUCCEEDED", execute: execute() },
      { type: "EXECUTE_FAILED", error: genericError },
      { type: "EXECUTE_FAILED", error: genericError, requiresNewPreview: true },
      { type: "SUBMIT_COMPOSE" },
      { type: "PREVIEW_SUCCEEDED", preview: p, confirmationToken: "new.token" },
      { type: "PREVIEW_FAILED", error: genericError },
      { type: "REQUEST_COMPARISON" },
      { type: "OPEN_TECHNICAL_DETAILS" },
      { type: "RETURN_TO_RESULT" },
      { type: "SET_TASK", task: "outra" },
      { type: "SET_PASTED_TEXT", text: "outro" },
    ];
    for (const event of events) {
      expect(flowReducer(approved, event)).toBe(approved);
    }
  });

  it("RESTART from approvedReview starts a fresh compose with no token carried over", () => {
    const next = flowReducer(approveReview(review), { type: "RESTART" });
    expect(next).toEqual({ screen: "compose", compose: initialComposeState, submitError: null });
  });
});

function compare(overrides: Partial<CompareResponse> = {}): CompareResponse {
  return {
    contract_version: "t20-application-api-v1",
    entries: [
      {
        strategy: "b0",
        treatment: "b0",
        recommended: false,
        unsafe_control_baseline: true,
        summary: { status: "allowed", categories: [], detected_span_count: 0, detected_categories: [] },
        external_payload: "conteudo original",
        payload_byte_count: 18,
      },
      {
        strategy: "b1",
        treatment: "b1",
        recommended: false,
        unsafe_control_baseline: false,
        summary: { status: "allowed", categories: [], detected_span_count: 0, detected_categories: [] },
        external_payload: "conteudo b1",
        payload_byte_count: 19,
      },
      {
        strategy: "b2",
        treatment: "b2",
        recommended: false,
        unsafe_control_baseline: false,
        summary: { status: "allowed", categories: [], detected_span_count: 0, detected_categories: [] },
        external_payload: "conteudo b2",
        payload_byte_count: 19,
      },
      {
        strategy: "b3",
        treatment: "b3",
        recommended: false,
        unsafe_control_baseline: false,
        summary: { status: "allowed", categories: [], detected_span_count: 0, detected_categories: [] },
        external_payload: "conteudo b3",
        payload_byte_count: 19,
      },
      {
        strategy: "b4",
        treatment: "b4",
        recommended: true,
        unsafe_control_baseline: false,
        summary: { status: "allowed", categories: [], detected_span_count: 0, detected_categories: [] },
        external_payload: "conteudo transformado",
        payload_byte_count: 21,
      },
    ],
    governance: {
      domain: "demo",
      purpose: "demo",
      policy_version: "v1",
      provider_class: "FakeProvider",
      requester_role: null,
      requested_pseudonym_scope: "session",
    },
    provider_mode: { provider_class: "FakeProvider" },
    ...overrides,
  };
}

describe("flowReducer -- result screen", () => {
  const p = preview();
  const e = execute();
  const state: FlowState = {
    screen: "result",
    compose: initialComposeState,
    preview: p,
    execute: e,
    compareError: null,
  };

  it("RESTART returns to a fresh compose screen", () => {
    const next = flowReducer(state, { type: "RESTART" });
    expect(next).toEqual({ screen: "compose", compose: initialComposeState, submitError: null });
  });

  it("REQUEST_COMPARISON moves to the comparing screen, carrying preview/execute forward", () => {
    const next = flowReducer(state, { type: "REQUEST_COMPARISON" });
    expect(next).toEqual({ screen: "comparing", compose: initialComposeState, preview: p, execute: e });
  });

  it("does not call/represent a comparison on any other event here", () => {
    expect(flowReducer(state, { type: "CONFIRM_REVIEW" })).toBe(state);
  });

  it("OPEN_TECHNICAL_DETAILS moves to the technicalDetails screen, carrying preview/execute/compareError forward -- no request involved", () => {
    const next = flowReducer(state, { type: "OPEN_TECHNICAL_DETAILS" });
    expect(next).toEqual({
      screen: "technicalDetails",
      compose: initialComposeState,
      preview: p,
      execute: e,
      compareError: null,
    });
  });

  it("OPEN_TECHNICAL_DETAILS preserves a prior compareError instead of silently clearing it", () => {
    const withError: FlowState = { ...state, compareError: genericError };
    const next = flowReducer(withError, { type: "OPEN_TECHNICAL_DETAILS" });
    expect(next).toEqual({
      screen: "technicalDetails",
      compose: initialComposeState,
      preview: p,
      execute: e,
      compareError: genericError,
    });
  });
});

describe("flowReducer -- technicalDetails screen (Ver detalhes técnicos)", () => {
  const p = preview();
  const e = execute();
  const state: FlowState = {
    screen: "technicalDetails",
    compose: initialComposeState,
    preview: p,
    execute: e,
    compareError: null,
  };

  it("RETURN_TO_RESULT goes back to result, preserving the original execute/preview and compareError untouched", () => {
    const next = flowReducer(state, { type: "RETURN_TO_RESULT" });
    expect(next).toEqual({
      screen: "result",
      compose: initialComposeState,
      preview: p,
      execute: e,
      compareError: null,
    });
  });

  it("RETURN_TO_RESULT restores a prior compareError rather than clearing it -- this screen never touches comparison state", () => {
    const withError: FlowState = { ...state, compareError: genericError };
    const next = flowReducer(withError, { type: "RETURN_TO_RESULT" });
    expect(next).toEqual({
      screen: "result",
      compose: initialComposeState,
      preview: p,
      execute: e,
      compareError: genericError,
    });
  });

  it("RESTART still returns to a fresh compose screen from the technicalDetails screen", () => {
    const next = flowReducer(state, { type: "RESTART" });
    expect(next).toEqual({ screen: "compose", compose: initialComposeState, submitError: null });
  });

  it("does not re-invoke preview/execute/compare from here -- those events are no-ops", () => {
    expect(flowReducer(state, { type: "CONFIRM_REVIEW" })).toBe(state);
    expect(flowReducer(state, { type: "EXECUTE_SUCCEEDED", execute: e })).toBe(state);
    expect(flowReducer(state, { type: "REQUEST_COMPARISON" })).toBe(state);
  });
});

describe("flowReducer -- comparing screen (the loading state for a comparison request)", () => {
  const p = preview();
  const e = execute();
  const state: FlowState = { screen: "comparing", compose: initialComposeState, preview: p, execute: e };

  it("COMPARE_SUCCEEDED moves to the comparison screen carrying the comparison payload", () => {
    const c = compare();
    const next = flowReducer(state, { type: "COMPARE_SUCCEEDED", comparison: c });
    expect(next).toEqual({
      screen: "comparison",
      compose: initialComposeState,
      preview: p,
      execute: e,
      comparison: c,
    });
  });

  it("COMPARE_FAILED returns to result (not a crash, not compose) carrying the error", () => {
    const next = flowReducer(state, { type: "COMPARE_FAILED", error: genericError });
    expect(next).toEqual({
      screen: "result",
      compose: initialComposeState,
      preview: p,
      execute: e,
      compareError: genericError,
    });
  });

  it("execute is not re-invoked from here -- CONFIRM_REVIEW/EXECUTE_* are no-ops", () => {
    expect(flowReducer(state, { type: "CONFIRM_REVIEW" })).toBe(state);
    expect(flowReducer(state, { type: "EXECUTE_SUCCEEDED", execute: e })).toBe(state);
  });
});

describe("flowReducer -- comparison screen", () => {
  const p = preview();
  const e = execute();
  const c = compare();
  const state: FlowState = {
    screen: "comparison",
    compose: initialComposeState,
    preview: p,
    execute: e,
    comparison: c,
  };

  it("RETURN_TO_RESULT goes back to result, preserving the original execute/preview and clearing any prior compare error", () => {
    const next = flowReducer(state, { type: "RETURN_TO_RESULT" });
    expect(next).toEqual({
      screen: "result",
      compose: initialComposeState,
      preview: p,
      execute: e,
      compareError: null,
    });
  });

  it("RESTART still returns to a fresh compose screen from the comparison screen", () => {
    const next = flowReducer(state, { type: "RESTART" });
    expect(next).toEqual({ screen: "compose", compose: initialComposeState, submitError: null });
  });
});

describe("isComposeReady", () => {
  it("example mode requires a chosen example id", () => {
    expect(isComposeReady({ ...initialComposeState, mode: "example", exampleId: null })).toBe(false);
    expect(isComposeReady({ ...initialComposeState, mode: "example", exampleId: "ex-1" })).toBe(true);
  });

  it("upload mode requires a file, backend vocabulary selection, and task", () => {
    expect(isComposeReady({ ...initialComposeState, mode: "upload", file: null })).toBe(false);
    expect(
      isComposeReady({
        ...initialComposeState,
        mode: "upload",
        file: { file: new File(["x"], "a.txt"), filename: "a.txt", byteSize: 1, displayType: "Texto simples" },
        documentType: "contract",
        analysisMode: "contract_summary",
        task: "resuma",
      }),
    ).toBe(true);
  });

  it("paste mode requires non-blank pasted text", () => {
    expect(isComposeReady({ ...initialComposeState, mode: "paste", pastedText: "   " })).toBe(false);
    expect(isComposeReady({ ...initialComposeState, mode: "paste", pastedText: "hi" })).toBe(true);
  });
});

describe("isSupportedUploadFilename", () => {
  it("accepts PDF, DOCX, TXT and MD, case-insensitively", () => {
    expect(isSupportedUploadFilename("contract.pdf")).toBe(true);
    expect(isSupportedUploadFilename("contract.docx")).toBe(true);
    expect(isSupportedUploadFilename("report.txt")).toBe(true);
    expect(isSupportedUploadFilename("REPORT.TXT")).toBe(true);
    expect(isSupportedUploadFilename("notes.md")).toBe(true);
  });

  it("rejects unsupported extensions", () => {
    expect(isSupportedUploadFilename("scan.png")).toBe(false);
    expect(isSupportedUploadFilename("sheet.xlsx")).toBe(false);
    expect(isSupportedUploadFilename("noextension")).toBe(false);
  });
});

describe("buildRequestBody", () => {
  it("sends example_id for example mode and never a strategy field", () => {
    const body = buildRequestBody({ ...initialComposeState, mode: "example", exampleId: "ex-1" });
    expect(body).toEqual({ example_id: "ex-1" });
    expect(body).not.toHaveProperty("strategy");
  });

  it("does not force binary upload into the historical JSON request", () => {
    const body = buildRequestBody({
      ...initialComposeState,
      mode: "upload",
      file: { file: new File(["# Title"], "doc.md"), filename: "doc.md", byteSize: 7, displayType: "Markdown" },
    });
    expect(body).toEqual({});
  });

  it("sends text for paste mode", () => {
    const body = buildRequestBody({ ...initialComposeState, mode: "paste", pastedText: "conteúdo" });
    expect(body).toEqual({ text: "conteúdo" });
  });

  it("includes a trimmed task only when non-blank", () => {
    const withTask = buildRequestBody({
      ...initialComposeState,
      mode: "paste",
      pastedText: "x",
      task: "  resuma isto  ",
    });
    expect(withTask.task).toBe("resuma isto");

    const withoutTask = buildRequestBody({
      ...initialComposeState,
      mode: "paste",
      pastedText: "x",
      task: "   ",
    });
    expect(withoutTask).not.toHaveProperty("task");
  });

  it("never sets a strategy field regardless of mode -- recommended is the default by omission", () => {
    const body = buildRequestBody({ ...initialComposeState, mode: "paste", pastedText: "x" });
    expect(Object.keys(body)).not.toContain("strategy");
  });
});
