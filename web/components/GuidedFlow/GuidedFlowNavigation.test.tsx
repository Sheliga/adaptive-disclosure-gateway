import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { resetVolatileLocaleForTests } from "@/i18n/LocaleProvider";
import {
  compareStrategies,
  executeDocument,
  executeDisclosure,
  getDemoFeatures,
  getDocumentTypes,
  getExamples,
  getHealth,
  previewDisclosure,
  previewDocument,
} from "@/lib/api";
import type { CompareResponse, ExecuteResponse, HealthResponse, PreviewResponse } from "@/lib/contracts";
import { copy } from "@/lib/copy";

import { GuidedFlow } from "./GuidedFlow";

vi.mock("@/lib/api", () => ({
  getHealth: vi.fn(),
  getExamples: vi.fn(),
  getDocumentTypes: vi.fn(),
  getDemoFeatures: vi.fn(),
  previewDisclosure: vi.fn(),
  executeDisclosure: vi.fn(),
  previewDocument: vi.fn(),
  executeDocument: vi.fn(),
  compareStrategies: vi.fn(),
}));

const mockedGetHealth = vi.mocked(getHealth);
const mockedGetExamples = vi.mocked(getExamples);
const mockedGetDocumentTypes = vi.mocked(getDocumentTypes);
const mockedGetDemoFeatures = vi.mocked(getDemoFeatures);
const mockedPreviewDisclosure = vi.mocked(previewDisclosure);
const mockedExecuteDisclosure = vi.mocked(executeDisclosure);
const mockedPreviewDocument = vi.mocked(previewDocument);
const mockedExecuteDocument = vi.mocked(executeDocument);
const mockedCompareStrategies = vi.mocked(compareStrategies);

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

/**
 * Spies on BOTH `Map.prototype.set` and `.delete`, and mirrors every write
 * that looks like a GuidedFlow history snapshot (a `flow-<n>` key holding a
 * FlowState-shaped value, i.e. an object with a `screen` field) into a
 * plain `Set`. Unlike asserting "delete was called with X", this tracks
 * actual retention: a snapshot counts as retained only until its OWN key is
 * deleted, so a test can assert an abandoned entry's id is (or is not)
 * still retained regardless of how many other Map writes happen around it.
 */
function trackRetainedFlowSnapshots() {
  const retained = new Set<string>();
  const values = new Map<string, unknown>();
  const isSnapshotKey = (key: unknown): key is string =>
    typeof key === "string" && /^flow-\d+$/.test(key);
  const isFlowStateValue = (value: unknown): boolean =>
    typeof value === "object" && value !== null && "screen" in value;
  const originalSet = Map.prototype.set;
  const originalDelete = Map.prototype.delete;
  const mapSet = vi
    .spyOn(Map.prototype, "set")
    .mockImplementation(function (this: Map<unknown, unknown>, key: unknown, value: unknown) {
      if (isSnapshotKey(key) && isFlowStateValue(value)) {
        retained.add(key);
        originalSet.call(values, key, value);
      }
      return originalSet.call(this, key, value);
    });
  const mapDelete = vi
    .spyOn(Map.prototype, "delete")
    .mockImplementation(function (this: Map<unknown, unknown>, key: unknown) {
      if (isSnapshotKey(key)) {
        retained.delete(key);
      }
      return originalDelete.call(this, key);
    });
  return {
    retained,
    /** The last FlowState snapshot written under `key` (whether or not still retained). */
    lastValue: (key: string) => values.get(key),
    restore: () => {
      mapSet.mockRestore();
      mapDelete.mockRestore();
    },
  };
}

/**
 * Records every `pushState`/`replaceState` GuidedFlow issues (by the
 * `flowNavigationId` it writes), interleaved with markers the test inserts,
 * so a test can assert on the ORDER of history writes relative to the
 * popstate events it dispatches -- e.g. that nothing was written while a
 * corrective `history.go(...)` was still pending. The real methods still
 * run, so jsdom's `history.state`/URL stay observable.
 */
function trackHistoryWrites() {
  const log: string[] = [];
  const originalPush = window.history.pushState.bind(window.history);
  const originalReplace = window.history.replaceState.bind(window.history);
  const idOf = (data: unknown) =>
    typeof data === "object" && data !== null && "flowNavigationId" in data
      ? String((data as { flowNavigationId: unknown }).flowNavigationId)
      : String(data);
  const push = vi
    .spyOn(window.history, "pushState")
    .mockImplementation((data: unknown, unused: string, url?: string | URL | null) => {
      log.push(`push:${idOf(data)}`);
      originalPush(data, unused, url);
    });
  const replace = vi
    .spyOn(window.history, "replaceState")
    .mockImplementation((data: unknown, unused: string, url?: string | URL | null) => {
      log.push(`replace:${idOf(data)}`);
      originalReplace(data, unused, url);
    });
  return {
    log,
    mark: (marker: string) => log.push(marker),
    restore: () => {
      push.mockRestore();
      replace.mockRestore();
    },
  };
}

function dispatchPopState(flowNavigationId: string) {
  act(() => {
    window.dispatchEvent(new PopStateEvent("popstate", { state: { flowNavigationId } }));
  });
}

/**
 * Drives Welcome -> Compose (example) -> Review -> Confirm and returns the
 * Compose and sending-Review navigation ids, with execute left pending on
 * whatever the caller's mock returns.
 */
async function reachPendingExampleSend() {
  await userEvent.click(screen.getByRole("button", { name: copy.howItWorks.ctaPrimary }));
  const composeId = window.history.state.flowNavigationId as string;
  await userEvent.selectOptions(await screen.findByLabelText(copy.newTest.exampleFieldLabel), "ex-1");
  await userEvent.click(screen.getByRole("button", { name: copy.newTest.continueToReview }));
  await screen.findByRole("heading", { name: copy.review.heading });
  const sendingReviewId = window.history.state.flowNavigationId as string;
  await userEvent.click(screen.getByRole("button", { name: copy.review.confirmSend }));
  return { composeId, sendingReviewId };
}

function expectNoComposeAndNoResend() {
  expect(screen.queryByRole("heading", { name: copy.newTest.heading })).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: copy.newTest.continueToReview }),
  ).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: copy.review.confirmSend })).not.toBeInTheDocument();
}

/**
 * T32.2 / #102: what "Result -> Back" must now show instead of the #105
 * fail-closed screen -- the read-only Approved Review. Equivalent-or-stronger
 * than the old assertions: no Confirm, no resend (no Compose, no Continue),
 * no Change, and none of the fail-closed/unrecoverable fallback either.
 */
async function expectApprovedReview() {
  expect(await screen.findByRole("heading", { name: copy.approvedReview.heading })).toBeInTheDocument();
  expect(screen.getByText(copy.approvedReview.sentBadge)).toBeInTheDocument();
  expect(screen.getByText(copy.approvedReview.readOnlyNotice)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: copy.review.confirmSend })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: copy.review.changeRequest })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: copy.newTest.continueToReview })).not.toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: copy.newTest.heading })).not.toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: copy.review.heading })).not.toBeInTheDocument();
  expect(
    screen.queryByRole("heading", { name: "Esta etapa não pode ser restaurada" }),
  ).not.toBeInTheDocument();
}

function compareResponse(): CompareResponse {
  return {
    contract_version: "t20-application-api-v1",
    entries: [],
    governance: previewResponse().governance,
    provider_mode: { provider_class: "FakeProvider" },
  };
}

function healthResponse(): HealthResponse {
  return {
    status: "ok",
    contract_version: "t20-application-api-v1",
    provider: {
      provider_class: "FakeProvider",
      model_id: "fake-1",
      model_snapshot: "2026-01-01",
      deterministic_demo_mode: true,
    },
    treatments_available: ["b0", "b1", "b2", "b3", "b4"],
  };
}

function previewResponse(): PreviewResponse {
  return {
    contract_version: "t20-application-api-v1",
    summary: {
      status: "allowed",
      categories: [],
      detected_span_count: 0,
      detected_categories: [],
    },
    external_payload: "conteudo transformado",
    payload_byte_count: 22,
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
  };
}

function executeResponse(): ExecuteResponse {
  return {
    contract_version: "t20-application-api-v1",
    status: "allowed",
    summary: previewResponse().summary,
    final_answer: "Resposta final reconstruida localmente.",
    provider: {
      called: true,
      provider_class: "FakeProvider",
      model_id: "fake-1",
      model_snapshot: "2026-01-01",
      decoding_config: null,
      transmitted_bytes: 22,
      response_hash: "hash",
      failed: false,
      failure_kind: null,
    },
    reconstruction: {
      attempted: true,
      reconstructed_hash: "hash2",
      changed_from_provider_response: false,
    },
    treatment: "b4",
    strategy: "recommended",
    governance: previewResponse().governance,
    total_ms: 100,
  };
}

function mockMatchMedia() {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })) as unknown as typeof window.matchMedia;
}

beforeEach(() => {
  vi.clearAllMocks();
  mockMatchMedia();
  window.history.replaceState(null, "", "/");
  window.localStorage.clear();
  window.sessionStorage.clear();
  resetVolatileLocaleForTests();
  mockedGetHealth.mockResolvedValue({ ok: true, data: healthResponse() });
  mockedGetExamples.mockResolvedValue({
    ok: true,
    data: {
      contract_version: "t20-application-api-v1",
      examples: [
        {
          example_id: "ex-1",
          title: "Contrato de exemplo",
          domain: "legal",
          purpose: "demo",
          task: "Resuma o contrato.",
          character_count: 400,
        },
      ],
    },
  });
  mockedGetDocumentTypes.mockResolvedValue({
    ok: true,
    data: {
      contract_version: "t20-application-api-v1",
      document_types: [
        {
          document_type: "contract",
          analysis_modes: ["contract_summary"],
          default_analysis_mode: "contract_summary",
        },
      ],
    },
  });
  mockedGetDemoFeatures.mockResolvedValue({
    ok: true,
    data: { demo_transparency_enabled: false, demo_vault_explorer_enabled: false },
  });
});

describe("GuidedFlow navigation foundation", () => {
  it("shows the primary journey, marks the current step, and focuses new headings", async () => {
    mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: previewResponse() });

    render(<GuidedFlow />);

    expect(screen.getByText("Introdução")).toBeInTheDocument();
    expect(screen.getByText("Preparar")).toBeInTheDocument();
    expect(screen.getByText("Revisar")).toBeInTheDocument();
    expect(screen.getByText("Enviar")).toBeInTheDocument();
    expect(screen.getByText("Resultado")).toBeInTheDocument();
    expect(screen.getByText("Introdução").closest("li")).toHaveAttribute("aria-current", "step");
    expect(document.activeElement).toBe(screen.getByRole("heading", { name: copy.howItWorks.title }));

    await userEvent.click(screen.getByRole("button", { name: copy.howItWorks.ctaPrimary }));
    const composeHeading = await screen.findByRole("heading", { name: copy.newTest.heading });
    expect(screen.getByText("Preparar").closest("li")).toHaveAttribute("aria-current", "step");
    expect(document.activeElement).toBe(composeHeading);

    await userEvent.selectOptions(await screen.findByLabelText(copy.newTest.exampleFieldLabel), "ex-1");
    await userEvent.click(screen.getByRole("button", { name: copy.newTest.continueToReview }));
    const reviewHeading = await screen.findByRole("heading", { name: copy.review.heading });
    expect(screen.getByText("Revisar").closest("li")).toHaveAttribute("aria-current", "step");
    expect(document.activeElement).toBe(reviewHeading);
  });

  it("goes back from Revisar to Preparar with compose data preserved and no execute call", async () => {
    mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: previewResponse() });
    render(<GuidedFlow />);

    await userEvent.click(screen.getByRole("button", { name: copy.howItWorks.ctaPrimary }));
    await userEvent.click(screen.getByRole("radio", { name: copy.entryModes.pasteText }));
    await userEvent.type(screen.getByLabelText(copy.newTest.pasteLabel), "Contrato com valor R$ 125.000,00");
    await userEvent.type(screen.getByLabelText(copy.newTest.taskLabel), "Resuma os riscos financeiros");
    await userEvent.click(screen.getByRole("button", { name: copy.newTest.continueToReview }));
    await screen.findByRole("heading", { name: copy.review.heading });

    await userEvent.click(screen.getByRole("button", { name: "Voltar" }));

    expect(screen.getByRole("radio", { name: copy.entryModes.pasteText })).toBeChecked();
    expect(screen.getByLabelText(copy.newTest.pasteLabel)).toHaveValue("Contrato com valor R$ 125.000,00");
    expect(screen.getByLabelText(copy.newTest.taskLabel)).toHaveValue("Resuma os riscos financeiros");
    expect(mockedPreviewDisclosure).toHaveBeenCalledTimes(1);
    expect(mockedExecuteDisclosure).not.toHaveBeenCalled();
  });

  it("maps browser Back/Forward to in-memory snapshots without replaying preview or execute", async () => {
    mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: previewResponse() });
    render(<GuidedFlow />);

    await userEvent.click(screen.getByRole("button", { name: copy.howItWorks.ctaPrimary }));
    await userEvent.selectOptions(await screen.findByLabelText(copy.newTest.exampleFieldLabel), "ex-1");
    await userEvent.click(screen.getByRole("button", { name: copy.newTest.continueToReview }));
    await screen.findByRole("heading", { name: copy.review.heading });

    window.history.back();
    await screen.findByRole("heading", { name: copy.newTest.heading });
    expect(mockedPreviewDisclosure).toHaveBeenCalledTimes(1);
    expect(mockedExecuteDisclosure).not.toHaveBeenCalled();

    window.history.forward();
    await screen.findByRole("heading", { name: copy.review.heading });
    expect(mockedPreviewDisclosure).toHaveBeenCalledTimes(1);
    expect(mockedExecuteDisclosure).not.toHaveBeenCalled();
    expect(window.location.search).not.toContain("ex-1");
  });

  it("keeps sensitive compose data out of URLs, history state, and Web Storage", async () => {
    mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: previewResponse() });
    const sensitiveDocument = "Contrato sigiloso: R$ 125.000,00";
    const sensitiveTask = "Resuma apenas para a diretoria";
    render(<GuidedFlow />);

    await userEvent.click(screen.getByRole("button", { name: copy.howItWorks.ctaPrimary }));
    await userEvent.click(screen.getByRole("radio", { name: copy.entryModes.pasteText }));
    await userEvent.type(screen.getByLabelText(copy.newTest.pasteLabel), sensitiveDocument);
    await userEvent.type(screen.getByLabelText(copy.newTest.taskLabel), sensitiveTask);

    expect(window.location.search).toBe("?step=prepare");
    expect(window.location.hash).toBe("");
    expect(window.history.state).toEqual({ flowNavigationId: expect.any(String) });
    expect(JSON.stringify(window.history.state)).not.toContain(sensitiveDocument);
    expect(JSON.stringify(window.history.state)).not.toContain(sensitiveTask);
    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.length).toBe(0);
  });

  it("fails closed on direct refresh of an unrecoverable ephemeral step", async () => {
    window.history.replaceState(null, "", "/?step=review");

    render(<GuidedFlow />);

    expect(await screen.findByRole("heading", { name: "Esta etapa não pode ser restaurada" })).toBeInTheDocument();
    expect(screen.getByText(/não salva documentos, tarefas, tokens ou payloads/i)).toBeInTheDocument();
    expect(mockedPreviewDisclosure).not.toHaveBeenCalled();
    expect(mockedExecuteDisclosure).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "Voltar à introdução" }));
    await screen.findByRole("heading", { name: copy.howItWorks.title });
  });

  it("does not replay execute or compare while navigating from Resultado to branches and back", async () => {
    mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: previewResponse() });
    mockedExecuteDisclosure.mockResolvedValue({ ok: true, data: executeResponse() });
    mockedCompareStrategies.mockResolvedValue({
      ok: false,
      status: 500,
      error: { message: copy.errors.generic, kind: null, fields: null },
    });

    render(<GuidedFlow />);
    await userEvent.click(screen.getByRole("button", { name: copy.howItWorks.ctaPrimary }));
    await userEvent.selectOptions(await screen.findByLabelText(copy.newTest.exampleFieldLabel), "ex-1");
    await userEvent.click(screen.getByRole("button", { name: copy.newTest.continueToReview }));
    await screen.findByRole("heading", { name: copy.review.heading });
    await userEvent.click(screen.getByRole("button", { name: copy.review.confirmSend }));
    await screen.findByRole("heading", { name: copy.result.heading });

    await userEvent.click(screen.getByRole("button", { name: copy.buttons.viewTechnicalDetails }));
    await screen.findByRole("heading", { name: copy.sectionHeadings.technicalDetails });
    await userEvent.click(screen.getByRole("button", { name: "Voltar" }));
    await screen.findByRole("heading", { name: copy.result.heading });

    await userEvent.click(screen.getByRole("button", { name: copy.buttons.compareStrategies }));
    await waitFor(() => expect(mockedCompareStrategies).toHaveBeenCalledTimes(1));
    await screen.findByRole("heading", { name: copy.result.heading });

    // #102: Result -> Back is the read-only Approved Review (was the #105
    // fail-closed screen), and Forward returns to Result without replay.
    window.history.back();
    await expectApprovedReview();
    window.history.forward();
    await screen.findByRole("heading", { name: copy.result.heading });

    expect(mockedPreviewDisclosure).toHaveBeenCalledTimes(1);
    expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1);
    expect(mockedCompareStrategies).toHaveBeenCalledTimes(1);
  });

  it("keeps the Compose snapshot across a pending preview and restores it with browser Back", async () => {
    const pendingPreview = deferred<Awaited<ReturnType<typeof previewDisclosure>>>();
    mockedPreviewDisclosure.mockReturnValue(pendingPreview.promise);
    render(<GuidedFlow />);

    await userEvent.click(screen.getByRole("button", { name: copy.howItWorks.ctaPrimary }));
    await userEvent.selectOptions(await screen.findByLabelText(copy.newTest.exampleFieldLabel), "ex-1");
    await userEvent.click(screen.getByRole("button", { name: copy.newTest.continueToReview }));
    await waitFor(() => expect(mockedPreviewDisclosure).toHaveBeenCalledTimes(1));

    pendingPreview.resolve({ ok: true, data: previewResponse() });
    await screen.findByRole("heading", { name: copy.review.heading });
    window.history.back();

    await screen.findByRole("heading", { name: copy.newTest.heading });
    expect(mockedPreviewDisclosure).toHaveBeenCalledTimes(1);
  });

  it("shows the Approved Review, never executing or a resend, when Back follows a pending send that resolved", async () => {
    mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: previewResponse() });
    const pendingExecute = deferred<Awaited<ReturnType<typeof executeDisclosure>>>();
    mockedExecuteDisclosure.mockReturnValue(pendingExecute.promise);
    render(<GuidedFlow />);

    await userEvent.click(screen.getByRole("button", { name: copy.howItWorks.ctaPrimary }));
    await userEvent.selectOptions(await screen.findByLabelText(copy.newTest.exampleFieldLabel), "ex-1");
    await userEvent.click(screen.getByRole("button", { name: copy.newTest.continueToReview }));
    await screen.findByRole("heading", { name: copy.review.heading });
    const sendingReviewId = window.history.state.flowNavigationId as string;
    await userEvent.click(screen.getByRole("button", { name: copy.review.confirmSend }));
    await waitFor(() => expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1));

    pendingExecute.resolve({ ok: true, data: executeResponse() });
    await screen.findByRole("heading", { name: copy.result.heading });
    dispatchPopState(sendingReviewId);

    await expectApprovedReview();
    expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1);
    expect(mockedCompareStrategies).not.toHaveBeenCalled();
  });

  it("keeps the Result snapshot across a pending compare and returns from Comparison without replay", async () => {
    mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: previewResponse() });
    mockedExecuteDisclosure.mockResolvedValue({ ok: true, data: executeResponse() });
    const pendingCompare = deferred<Awaited<ReturnType<typeof compareStrategies>>>();
    mockedCompareStrategies.mockReturnValue(pendingCompare.promise);
    render(<GuidedFlow />);

    await userEvent.click(screen.getByRole("button", { name: copy.howItWorks.ctaPrimary }));
    await userEvent.selectOptions(await screen.findByLabelText(copy.newTest.exampleFieldLabel), "ex-1");
    await userEvent.click(screen.getByRole("button", { name: copy.newTest.continueToReview }));
    await screen.findByRole("heading", { name: copy.review.heading });
    await userEvent.click(screen.getByRole("button", { name: copy.review.confirmSend }));
    await screen.findByRole("heading", { name: copy.result.heading });
    await userEvent.click(screen.getByRole("button", { name: copy.buttons.compareStrategies }));
    await waitFor(() => expect(mockedCompareStrategies).toHaveBeenCalledTimes(1));

    pendingCompare.resolve({ ok: true, data: compareResponse() });
    await screen.findByRole("heading", { name: copy.comparison.heading });
    await userEvent.click(screen.getByRole("button", { name: copy.comparison.backToResult }));

    await screen.findByRole("heading", { name: copy.result.heading });
    expect(mockedCompareStrategies).toHaveBeenCalledTimes(1);
  });

  it("reuses the Compose navigation id and snapshot entry while fields change", async () => {
    const mapSet = vi.spyOn(Map.prototype, "set");
    render(<GuidedFlow />);
    await userEvent.click(screen.getByRole("button", { name: copy.howItWorks.ctaPrimary }));
    const initialNavigationId = window.history.state.flowNavigationId as string;
    mapSet.mockClear();

    await userEvent.click(screen.getByRole("radio", { name: copy.entryModes.pasteText }));
    await userEvent.type(screen.getByLabelText(copy.newTest.pasteLabel), "primeira alteração");
    expect(window.history.state.flowNavigationId).toBe(initialNavigationId);

    await userEvent.clear(screen.getByLabelText(copy.newTest.pasteLabel));
    await userEvent.type(screen.getByLabelText(copy.newTest.pasteLabel), "valor final preservado");
    expect(window.history.state.flowNavigationId).toBe(initialNavigationId);
    expect(screen.getByLabelText(copy.newTest.pasteLabel)).toHaveValue("valor final preservado");

    const flowSnapshotIds = mapSet.mock.calls
      .map(([key]) => key)
      .filter((key) => typeof key === "string" && key.startsWith("flow-"));
    expect(new Set(flowSnapshotIds)).toEqual(new Set([initialNavigationId]));
    mapSet.mockRestore();
  });

  it("uses the same history traversal for Review and Technical Details back buttons", async () => {
    mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: previewResponse() });
    mockedExecuteDisclosure.mockResolvedValue({ ok: true, data: executeResponse() });
    render(<GuidedFlow />);

    await userEvent.click(screen.getByRole("button", { name: copy.howItWorks.ctaPrimary }));
    await userEvent.selectOptions(await screen.findByLabelText(copy.newTest.exampleFieldLabel), "ex-1");
    await userEvent.click(screen.getByRole("button", { name: copy.newTest.continueToReview }));
    await screen.findByRole("heading", { name: copy.review.heading });
    await userEvent.click(screen.getByRole("button", { name: "Voltar" }));
    await screen.findByRole("heading", { name: copy.newTest.heading });
    window.history.back();
    await screen.findByRole("heading", { name: copy.howItWorks.title });

    await userEvent.click(screen.getByRole("button", { name: copy.howItWorks.ctaPrimary }));
    await userEvent.selectOptions(await screen.findByLabelText(copy.newTest.exampleFieldLabel), "ex-1");
    await userEvent.click(screen.getByRole("button", { name: copy.newTest.continueToReview }));
    await screen.findByRole("heading", { name: copy.review.heading });
    await userEvent.click(screen.getByRole("button", { name: copy.review.confirmSend }));
    await screen.findByRole("heading", { name: copy.result.heading });
    await userEvent.click(screen.getByRole("button", { name: copy.buttons.viewTechnicalDetails }));
    await screen.findByRole("heading", { name: copy.sectionHeadings.technicalDetails });
    await userEvent.click(screen.getByRole("button", { name: copy.technicalDetails.backToResult }));
    await screen.findByRole("heading", { name: copy.result.heading });
    window.history.back();

    await expectApprovedReview();
    expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1);
  });

  it("prunes a discarded Review snapshot before creating a new forward branch", async () => {
    mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: previewResponse() });
    const tracker = trackRetainedFlowSnapshots();
    render(<GuidedFlow />);

    await userEvent.click(screen.getByRole("button", { name: copy.howItWorks.ctaPrimary }));
    await userEvent.selectOptions(await screen.findByLabelText(copy.newTest.exampleFieldLabel), "ex-1");
    await userEvent.click(screen.getByRole("button", { name: copy.newTest.continueToReview }));
    await screen.findByRole("heading", { name: copy.review.heading });
    const abandonedReviewId = window.history.state.flowNavigationId as string;
    expect(tracker.retained.has(abandonedReviewId)).toBe(true);

    window.history.back();
    await screen.findByRole("heading", { name: copy.newTest.heading });
    await userEvent.click(screen.getByRole("button", { name: copy.newTest.continueToReview }));
    await screen.findByRole("heading", { name: copy.review.heading });

    expect(window.history.state.flowNavigationId).not.toBe(abandonedReviewId);
    expect(tracker.retained.has(abandonedReviewId)).toBe(false);

    // A synthetic popstate to the abandoned id must not resurrect the old
    // Review: its snapshot is gone, so the flow falls back to the
    // unrecoverable screen instead of silently restoring stale data.
    window.dispatchEvent(
      new PopStateEvent("popstate", { state: { flowNavigationId: abandonedReviewId } }),
    );
    expect(
      await screen.findByRole("heading", { name: "Esta etapa não pode ser restaurada" }),
    ).toBeInTheDocument();

    tracker.restore();
  });

  it("prunes the Approved Review and Result snapshots when a new branch starts from the historical Compose", async () => {
    mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: previewResponse() });
    mockedExecuteDisclosure.mockResolvedValue({ ok: true, data: executeResponse() });
    const tracker = trackRetainedFlowSnapshots();
    render(<GuidedFlow />);

    await userEvent.click(screen.getByRole("button", { name: copy.howItWorks.ctaPrimary }));
    await userEvent.selectOptions(await screen.findByLabelText(copy.newTest.exampleFieldLabel), "ex-1");
    await userEvent.click(screen.getByRole("button", { name: copy.newTest.continueToReview }));
    await screen.findByRole("heading", { name: copy.review.heading });
    await userEvent.click(screen.getByRole("button", { name: copy.review.confirmSend }));
    await screen.findByRole("heading", { name: copy.result.heading });
    const resultId = window.history.state.flowNavigationId as string;
    expect(tracker.retained.has(resultId)).toBe(true);

    // Compose -> Review -> Confirm -> Result -> Back lands on the sent
    // Review entry, now the read-only Approved Review (#102).
    window.history.back();
    await expectApprovedReview();
    const approvedId = window.history.state.flowNavigationId as string;
    expect(tracker.retained.has(approvedId)).toBe(true);

    // Back once more to the historical Compose, then start a new branch
    // from it: nothing external happens until the user continues, and the
    // new Review is reached only through a fresh preview.
    window.history.back();
    await screen.findByRole("heading", { name: copy.newTest.heading });
    expect(mockedPreviewDisclosure).toHaveBeenCalledTimes(1);
    await userEvent.click(screen.getByRole("button", { name: copy.newTest.continueToReview }));
    await screen.findByRole("heading", { name: copy.review.heading });
    expect(mockedPreviewDisclosure).toHaveBeenCalledTimes(2);

    // Both abandoned entries -- the Approved Review and the Result carrying
    // the execute payload -- must be gone once the new branch is pushed.
    expect(tracker.retained.has(approvedId)).toBe(false);
    expect(tracker.retained.has(resultId)).toBe(false);
    expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1);

    tracker.restore();
  });

  it("computes the exact delta to correct a multi-step Back during a pending send", async () => {
    mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: previewResponse() });
    const pendingExecute = deferred<Awaited<ReturnType<typeof executeDisclosure>>>();
    mockedExecuteDisclosure.mockReturnValue(pendingExecute.promise);
    render(<GuidedFlow />);

    await userEvent.click(screen.getByRole("button", { name: copy.howItWorks.ctaPrimary }));
    await userEvent.selectOptions(await screen.findByLabelText(copy.newTest.exampleFieldLabel), "ex-1");
    await userEvent.click(screen.getByRole("button", { name: copy.newTest.continueToReview }));
    await screen.findByRole("heading", { name: copy.review.heading });
    const sendingReviewId = window.history.state.flowNavigationId as string;
    await userEvent.click(screen.getByRole("button", { name: copy.review.confirmSend }));
    await waitFor(() => expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1));

    // Simulate a multi-step Back that lands two entries behind the sending
    // Review (e.g. two presses collapsed into one browser navigation, or an
    // explicit history.go(-2)): the browser now reports the very first
    // tracked entry ("flow-0"), two steps before the sending Review
    // ("flow-2"). The real `window.history.go` is stubbed out so the test
    // observes exactly what GuidedFlow asks the browser to do, rather than
    // depending on jsdom's own navigation timing.
    const goSpy = vi.spyOn(window.history, "go").mockImplementation(() => {});
    window.dispatchEvent(new PopStateEvent("popstate", { state: { flowNavigationId: "flow-0" } }));

    // A single history.go(1) correction (the old hard-coded behavior) would
    // land one entry short of the sending Review; the fix must compute the
    // exact distance back (historyIndexRef.current - targetIndex = 2).
    expect(goSpy).toHaveBeenCalledWith(2);
    expect(screen.queryByRole("heading", { name: copy.newTest.heading })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: copy.review.confirmSend })).not.toBeInTheDocument();
    expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1);
    goSpy.mockRestore();

    // The corrective go(2) landing back on the sending entry must be
    // swallowed -- but only that specific popstate, not a bare flag that
    // would also eat an unrelated one.
    window.dispatchEvent(
      new PopStateEvent("popstate", { state: { flowNavigationId: sendingReviewId } }),
    );
    expect(screen.queryByRole("heading", { name: copy.newTest.heading })).not.toBeInTheDocument();

    pendingExecute.resolve({ ok: true, data: executeResponse() });
    await screen.findByRole("heading", { name: copy.result.heading });

    // Back to the sent Review entry, again via a synthetic popstate (see
    // the comment above `goSpy`): its snapshot was converted to the
    // read-only Approved Review the moment the send succeeded (#102).
    window.dispatchEvent(
      new PopStateEvent("popstate", { state: { flowNavigationId: sendingReviewId } }),
    );
    await expectApprovedReview();
    expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1);
  });

  it("does not present a pending send as cancelled when Back reaches an unrecognized history entry", async () => {
    mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: previewResponse() });
    const pendingExecute = deferred<Awaited<ReturnType<typeof executeDisclosure>>>();
    mockedExecuteDisclosure.mockReturnValue(pendingExecute.promise);
    render(<GuidedFlow />);

    await userEvent.click(screen.getByRole("button", { name: copy.howItWorks.ctaPrimary }));
    await userEvent.selectOptions(await screen.findByLabelText(copy.newTest.exampleFieldLabel), "ex-1");
    await userEvent.click(screen.getByRole("button", { name: copy.newTest.continueToReview }));
    await screen.findByRole("heading", { name: copy.review.heading });
    await userEvent.click(screen.getByRole("button", { name: copy.review.confirmSend }));
    await waitFor(() => expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1));

    const goSpy = vi.spyOn(window.history, "go").mockImplementation(() => {});
    // An id this session never tracked (e.g. a stale entry surviving a
    // reload) -- targetIndex resolves to -1.
    window.dispatchEvent(
      new PopStateEvent("popstate", { state: { flowNavigationId: "unknown-entry" } }),
    );

    // Neither Compose (a resend-from-scratch affordance) nor the generic
    // unrecoverable screen may stand in for "the send is still in flight" --
    // both would read to the user as their pending send having been
    // cancelled or lost.
    expect(goSpy).toHaveBeenCalledWith(1);
    expect(screen.queryByRole("heading", { name: copy.newTest.heading })).not.toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Esta etapa não pode ser restaurada" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: copy.review.confirmSend })).not.toBeInTheDocument();
    expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1);
    goSpy.mockRestore();
  });

  it("keeps a pending send in progress when browser Back is attempted", async () => {
    mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: previewResponse() });
    const pendingExecute = deferred<Awaited<ReturnType<typeof executeDisclosure>>>();
    mockedExecuteDisclosure.mockReturnValue(pendingExecute.promise);
    render(<GuidedFlow />);

    await userEvent.click(screen.getByRole("button", { name: copy.howItWorks.ctaPrimary }));
    const composeNavigationId = window.history.state.flowNavigationId as string;
    await userEvent.selectOptions(await screen.findByLabelText(copy.newTest.exampleFieldLabel), "ex-1");
    await userEvent.click(screen.getByRole("button", { name: copy.newTest.continueToReview }));
    await screen.findByRole("heading", { name: copy.review.heading });
    const sendingReviewId = window.history.state.flowNavigationId as string;
    await userEvent.click(screen.getByRole("button", { name: copy.review.confirmSend }));
    await waitFor(() => expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1));

    // Simulate the browser having navigated Back to Compose while the send
    // is in flight, via a synthetic popstate rather than jsdom's own
    // `history.back()` task queue -- which defers/interleaves unpredictably
    // relative to the pending-promise resolution later in this test, making
    // the real navigation APIs nondeterministic here. This is the same
    // technique used elsewhere for popstate assertions.
    const goSpy = vi.spyOn(window.history, "go").mockImplementation(() => {});
    window.dispatchEvent(
      new PopStateEvent("popstate", { state: { flowNavigationId: composeNavigationId } }),
    );
    expect(goSpy).toHaveBeenCalledWith(1);
    goSpy.mockRestore();

    // The corrective go(1) landing back on the sending Review must be
    // swallowed, keeping the flow on "executing" rather than falling back
    // to Compose or offering a resend on Review.
    window.dispatchEvent(
      new PopStateEvent("popstate", { state: { flowNavigationId: sendingReviewId } }),
    );
    expect(screen.queryByRole("heading", { name: copy.newTest.heading })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: copy.review.confirmSend })).not.toBeInTheDocument();
    expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1);

    pendingExecute.resolve({ ok: true, data: executeResponse() });
    await screen.findByRole("heading", { name: copy.result.heading });

    // Back to the sent Review entry, again via a synthetic popstate for the
    // same determinism reason as above: its snapshot was converted to the
    // read-only Approved Review the moment the send succeeded (#102).
    window.dispatchEvent(
      new PopStateEvent("popstate", { state: { flowNavigationId: sendingReviewId } }),
    );
    await expectApprovedReview();
    expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1);
  });

  it("does not restore processing or offer a post-send re-execution path with browser Back", async () => {
    mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: previewResponse() });
    mockedExecuteDisclosure.mockResolvedValue({ ok: true, data: executeResponse() });
    render(<GuidedFlow />);

    await userEvent.click(screen.getByRole("button", { name: copy.howItWorks.ctaPrimary }));
    await userEvent.selectOptions(await screen.findByLabelText(copy.newTest.exampleFieldLabel), "ex-1");
    await userEvent.click(screen.getByRole("button", { name: copy.newTest.continueToReview }));
    await screen.findByRole("heading", { name: copy.review.heading });
    await userEvent.click(screen.getByRole("button", { name: copy.review.confirmSend }));
    await screen.findByRole("heading", { name: copy.result.heading });

    window.history.back();

    await expectApprovedReview();
    expect(mockedPreviewDisclosure).toHaveBeenCalledTimes(1);
    expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1);
    expect(mockedCompareStrategies).not.toHaveBeenCalled();
  });

  /**
   * Race: execute completion vs history correction.
   *
   * A Back during "executing" makes GuidedFlow ask the browser to return to
   * the sending Review with `history.go(delta)`. In a real browser that
   * correction lands asynchronously, so execute can settle while the browser
   * is still physically on the earlier entry. The event order below is
   * therefore built by hand: `history.go` is stubbed to a no-op (it must not
   * emit popstate on its own), the out-of-band Back and the later corrective
   * landing are synthetic popstate events, and execute is resolved BETWEEN
   * them. jsdom's own traversal queue cannot produce this interleaving
   * deterministically (see the other synthetic-popstate tests above), and
   * since the stub keeps jsdom physically on the Review entry, what the test
   * observes is the ORDER of history writes relative to those two events.
   */
  it("registers Result only after the corrective popstate when execute resolves while a Back correction is pending", async () => {
    mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: previewResponse() });
    const pendingExecute = deferred<Awaited<ReturnType<typeof executeDisclosure>>>();
    mockedExecuteDisclosure.mockReturnValue(pendingExecute.promise);
    const tracker = trackRetainedFlowSnapshots();
    const goSpy = vi.spyOn(window.history, "go").mockImplementation(() => {});
    let writes: ReturnType<typeof trackHistoryWrites> | null = null;
    try {
      render(<GuidedFlow />);
      const welcomeId = window.history.state.flowNavigationId as string;
      const { composeId, sendingReviewId } = await reachPendingExampleSend();
      await waitFor(() => expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1));

      writes = trackHistoryWrites();
      writes.mark("back-popstate");
      dispatchPopState(composeId);
      expect(goSpy).toHaveBeenCalledTimes(1);
      expect(goSpy).toHaveBeenCalledWith(1);
      expectNoComposeAndNoResend();

      // Execute settles BEFORE the corrective popstate: the browser is still
      // on Compose, so nothing may be written to history yet.
      pendingExecute.resolve({ ok: true, data: executeResponse() });
      await screen.findByRole("heading", { name: copy.result.heading });
      expectNoComposeAndNoResend();
      expect(writes.log).toEqual(["back-popstate"]);
      expect(window.history.state.flowNavigationId).toBe(sendingReviewId);

      writes.mark("corrective-popstate");
      dispatchPopState(sendingReviewId);
      await waitFor(() =>
        expect(window.history.state.flowNavigationId).not.toBe(sendingReviewId),
      );
      const resultId = window.history.state.flowNavigationId as string;
      // Result is written exactly once, as a push, only after the browser is
      // back on the sending Review -- so its entry directly follows it.
      expect(writes.log).toEqual(["back-popstate", "corrective-popstate", `push:${resultId}`]);
      expect(window.location.search).toBe("?step=result");
      expect(screen.getByRole("heading", { name: copy.result.heading })).toBeInTheDocument();
      expect(goSpy).toHaveBeenCalledTimes(1);

      // Back from Result lands on the sent Review entry: the read-only
      // Approved Review (#102), never Compose and never a resend.
      dispatchPopState(sendingReviewId);
      await expectApprovedReview();
      expectNoComposeAndNoResend();
      expect(goSpy).toHaveBeenCalledTimes(1);

      // Forward from there returns to the registered Result without
      // re-executing the provider.
      dispatchPopState(resultId);
      await screen.findByRole("heading", { name: copy.result.heading });
      expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1);
      expect(mockedPreviewDisclosure).toHaveBeenCalledTimes(1);
      expect(writes.log.filter((entry) => entry.startsWith("push:"))).toEqual([`push:${resultId}`]);

      // The sent Review's snapshot was converted in place, not duplicated:
      // exactly the four reachable entries remain, and the one at the sent
      // Review's id is the token-free Approved Review.
      expect([...tracker.retained].sort()).toEqual(
        [welcomeId, composeId, sendingReviewId, resultId].sort(),
      );
      expect(tracker.lastValue(sendingReviewId)).toMatchObject({ screen: "approvedReview" });
      expect(tracker.lastValue(sendingReviewId)).not.toHaveProperty("confirmationToken");
    } finally {
      writes?.restore();
      goSpy.mockRestore();
      tracker.restore();
    }
  });

  it("keeps a failed send attached to the sending Review when execute fails while a Back correction is pending", async () => {
    mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: previewResponse() });
    const pendingExecute = deferred<Awaited<ReturnType<typeof executeDisclosure>>>();
    mockedExecuteDisclosure.mockReturnValue(pendingExecute.promise);
    const goSpy = vi.spyOn(window.history, "go").mockImplementation(() => {});
    let writes: ReturnType<typeof trackHistoryWrites> | null = null;
    try {
      render(<GuidedFlow />);
      const { composeId, sendingReviewId } = await reachPendingExampleSend();
      await waitFor(() => expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1));

      // Same artificial ordering as the success-path race test above.
      writes = trackHistoryWrites();
      writes.mark("back-popstate");
      dispatchPopState(composeId);
      expect(goSpy).toHaveBeenCalledWith(1);

      pendingExecute.resolve({
        ok: false,
        status: 502,
        error: { message: copy.errors.generic, kind: null, fields: null },
      });
      await screen.findByText(copy.errors.generic);
      expect(screen.queryByRole("heading", { name: copy.newTest.heading })).not.toBeInTheDocument();
      // The browser is still on Compose: writing the Review-with-error now
      // would overwrite (replace) or fork (push) the wrong entry.
      expect(writes.log).toEqual(["back-popstate"]);

      writes.mark("corrective-popstate");
      dispatchPopState(sendingReviewId);
      await waitFor(() =>
        expect(writes?.log).toEqual([
          "back-popstate",
          "corrective-popstate",
          `replace:${sendingReviewId}`,
        ]),
      );
      expect(window.history.state.flowNavigationId).toBe(sendingReviewId);
      expect(window.location.search).toBe("?step=review");
      expect(screen.getByRole("heading", { name: copy.review.heading })).toBeInTheDocument();
      expect(screen.getByText(copy.errors.generic)).toBeInTheDocument();
      expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1);
      expect(goSpy).toHaveBeenCalledTimes(1);
    } finally {
      writes?.restore();
      goSpy.mockRestore();
    }
  });

  it("re-corrects a second Back that arrives after execute resolved but before the first correction landed", async () => {
    mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: previewResponse() });
    const pendingExecute = deferred<Awaited<ReturnType<typeof executeDisclosure>>>();
    mockedExecuteDisclosure.mockReturnValue(pendingExecute.promise);
    const goSpy = vi.spyOn(window.history, "go").mockImplementation(() => {});
    let writes: ReturnType<typeof trackHistoryWrites> | null = null;
    try {
      render(<GuidedFlow />);
      const welcomeId = window.history.state.flowNavigationId as string;
      const { composeId, sendingReviewId } = await reachPendingExampleSend();
      await waitFor(() => expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1));

      // Same artificial ordering as the race tests above.
      writes = trackHistoryWrites();
      dispatchPopState(composeId);
      expect(goSpy).toHaveBeenLastCalledWith(1);
      pendingExecute.resolve({ ok: true, data: executeResponse() });
      await screen.findByRole("heading", { name: copy.result.heading });

      // A second Back lands on Welcome before the first correction does. The
      // flow is no longer "executing", but the browser is still not on the
      // sending Review: this must be corrected (exact delta 2), not restored
      // as Welcome -- which would also drop the unsynced Result.
      dispatchPopState(welcomeId);
      expect(goSpy).toHaveBeenLastCalledWith(2);
      expect(screen.queryByRole("heading", { name: copy.howItWorks.title })).not.toBeInTheDocument();
      expectNoComposeAndNoResend();
      expect(writes.log).toEqual([]);

      dispatchPopState(sendingReviewId);
      await waitFor(() => expect(writes?.log).toHaveLength(1));
      const resultId = window.history.state.flowNavigationId as string;
      expect(writes.log).toEqual([`push:${resultId}`]);
      expect(resultId).not.toBe(sendingReviewId);
      expect(screen.getByRole("heading", { name: copy.result.heading })).toBeInTheDocument();
      expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1);
    } finally {
      writes?.restore();
      goSpy.mockRestore();
    }
  });

  it("does not restore the sending Review when a popstate lands on its own entry during a pending send", async () => {
    mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: previewResponse() });
    const pendingExecute = deferred<Awaited<ReturnType<typeof executeDisclosure>>>();
    mockedExecuteDisclosure.mockReturnValue(pendingExecute.promise);
    const goSpy = vi.spyOn(window.history, "go").mockImplementation(() => {});
    try {
      render(<GuidedFlow />);
      const { sendingReviewId } = await reachPendingExampleSend();
      await waitFor(() => expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1));

      // Synthetic, for the same determinism reason as the other popstate
      // tests: a popstate reporting the sending entry itself while no
      // correction is outstanding. The Review snapshot is still held at
      // this point (it is only dropped once the send succeeds), so handling
      // this as an ordinary restore would put Confirm back on screen.
      dispatchPopState(sendingReviewId);
      expect(goSpy).not.toHaveBeenCalled();
      expectNoComposeAndNoResend();
      expect(screen.queryByRole("heading", { name: copy.review.heading })).not.toBeInTheDocument();

      pendingExecute.resolve({ ok: true, data: executeResponse() });
      await screen.findByRole("heading", { name: copy.result.heading });
      expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1);
    } finally {
      goSpy.mockRestore();
    }
  });

  it("writes no history after unmount while a Back correction is still pending", async () => {
    mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: previewResponse() });
    const pendingExecute = deferred<Awaited<ReturnType<typeof executeDisclosure>>>();
    mockedExecuteDisclosure.mockReturnValue(pendingExecute.promise);
    const goSpy = vi.spyOn(window.history, "go").mockImplementation(() => {});
    let writes: ReturnType<typeof trackHistoryWrites> | null = null;
    try {
      const { unmount } = render(<GuidedFlow />);
      const { composeId, sendingReviewId } = await reachPendingExampleSend();
      await waitFor(() => expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1));

      dispatchPopState(composeId);
      expect(goSpy).toHaveBeenCalledWith(1);
      unmount();

      // Execute settling and the correction landing after unmount must be
      // inert: no throw, and nothing written into a history the component
      // no longer owns.
      writes = trackHistoryWrites();
      await act(async () => {
        pendingExecute.resolve({ ok: true, data: executeResponse() });
        await pendingExecute.promise;
      });
      dispatchPopState(sendingReviewId);
      expect(writes.log).toEqual([]);
      expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1);
    } finally {
      writes?.restore();
      goSpy.mockRestore();
    }
  });

  it("registers an uploaded document's Result only after the corrective popstate when executeDocument resolves first", async () => {
    mockedPreviewDocument.mockResolvedValue({
      ok: true,
      data: { ...previewResponse(), confirmation_token: "opaque.confirmation.token" },
    });
    const pendingExecute = deferred<Awaited<ReturnType<typeof executeDocument>>>();
    mockedExecuteDocument.mockReturnValue(pendingExecute.promise);
    const goSpy = vi.spyOn(window.history, "go").mockImplementation(() => {});
    let writes: ReturnType<typeof trackHistoryWrites> | null = null;
    try {
      render(<GuidedFlow />);
      await userEvent.click(screen.getByRole("button", { name: copy.howItWorks.ctaPrimary }));
      const composeId = window.history.state.flowNavigationId as string;
      await userEvent.click(screen.getByRole("radio", { name: copy.entryModes.uploadFile }));
      await userEvent.upload(
        screen.getByLabelText(copy.newTest.uploadFieldLabel),
        new File([new Uint8Array([0x25, 0x50, 0x44, 0x46])], "synthetic-contract.pdf", {
          type: "application/pdf",
        }),
      );
      await userEvent.type(screen.getByLabelText(copy.newTest.taskLabel), "Quais são os prazos?");
      await userEvent.click(screen.getByRole("button", { name: copy.newTest.continueToReview }));
      await screen.findByRole("heading", { name: copy.review.heading });
      const sendingReviewId = window.history.state.flowNavigationId as string;
      await userEvent.click(screen.getByRole("button", { name: copy.review.confirmSend }));
      await waitFor(() => expect(mockedExecuteDocument).toHaveBeenCalledTimes(1));

      // Same artificial ordering as the paste/example race test above.
      writes = trackHistoryWrites();
      writes.mark("back-popstate");
      dispatchPopState(composeId);
      expect(goSpy).toHaveBeenCalledWith(1);

      pendingExecute.resolve({ ok: true, data: executeResponse() });
      await screen.findByRole("heading", { name: copy.result.heading });
      expectNoComposeAndNoResend();
      expect(writes.log).toEqual(["back-popstate"]);

      writes.mark("corrective-popstate");
      dispatchPopState(sendingReviewId);
      await waitFor(() =>
        expect(window.history.state.flowNavigationId).not.toBe(sendingReviewId),
      );
      const resultId = window.history.state.flowNavigationId as string;
      expect(writes.log).toEqual(["back-popstate", "corrective-popstate", `push:${resultId}`]);

      // #102: the upload path gets the same Approved Review through the
      // same mechanism as paste/example, and it holds no token.
      dispatchPopState(sendingReviewId);
      await expectApprovedReview();
      expectNoComposeAndNoResend();
      expect(screen.getByText("synthetic-contract.pdf")).toBeInTheDocument();

      // Forward returns to the registered Result without calling anything.
      dispatchPopState(resultId);
      await screen.findByRole("heading", { name: copy.result.heading });
      expect(mockedExecuteDocument).toHaveBeenCalledTimes(1);
      expect(mockedPreviewDocument).toHaveBeenCalledTimes(1);
    } finally {
      writes?.restore();
      goSpy.mockRestore();
    }
  });

  /**
   * Result-action lock during a pending correction (#101 follow-up).
   *
   * Execute can settle to Result BEFORE the corrective popstate lands (see
   * the race test above): Result renders and its actions are clickable, but
   * `historyCorrectionRef.current` is still non-null, so the browser is not
   * actually at `currentNavigationIdRef` yet. Opening Technical Details,
   * requesting Comparison, or Restarting in that window would dispatch
   * straight into the history-sync effect's push branch relative to the
   * WRONG entry (the sending Review, not yet the settled Result), forking
   * history without ever registering Result. This test drives exactly that
   * window and asserts the three actions are inert until the correction
   * lands.
   */
  it("blocks Technical Details, Compare, and Restart on Result while a Back correction is pending", async () => {
    mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: previewResponse() });
    const pendingExecute = deferred<Awaited<ReturnType<typeof executeDisclosure>>>();
    mockedExecuteDisclosure.mockReturnValue(pendingExecute.promise);
    const goSpy = vi.spyOn(window.history, "go").mockImplementation(() => {});
    let writes: ReturnType<typeof trackHistoryWrites> | null = null;
    try {
      render(<GuidedFlow />);
      const { composeId } = await reachPendingExampleSend();
      await waitFor(() => expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1));

      dispatchPopState(composeId);
      expect(goSpy).toHaveBeenCalledWith(1);

      // Execute settles BEFORE the corrective popstate: Result renders, but
      // the correction is still pending.
      pendingExecute.resolve({ ok: true, data: executeResponse() });
      await screen.findByRole("heading", { name: copy.result.heading });

      writes = trackHistoryWrites();

      // Technical Details: still on Result, no history write, no Technical
      // Details branch, execute not called again.
      await userEvent.click(screen.getByRole("button", { name: copy.buttons.viewTechnicalDetails }));
      expect(screen.getByRole("heading", { name: copy.result.heading })).toBeInTheDocument();
      expect(
        screen.queryByRole("heading", { name: copy.sectionHeadings.technicalDetails }),
      ).not.toBeInTheDocument();
      expect(writes.log).toEqual([]);

      // Compare: compareStrategies is never called, no history write.
      await userEvent.click(screen.getByRole("button", { name: copy.buttons.compareStrategies }));
      expect(mockedCompareStrategies).not.toHaveBeenCalled();
      expect(screen.getByRole("heading", { name: copy.result.heading })).toBeInTheDocument();
      expect(writes.log).toEqual([]);

      // Restart: no Compose, Result stays, history unchanged.
      await userEvent.click(screen.getByRole("button", { name: copy.result.restart }));
      expect(screen.queryByRole("heading", { name: copy.newTest.heading })).not.toBeInTheDocument();
      expect(screen.getByRole("heading", { name: copy.result.heading })).toBeInTheDocument();
      expect(writes.log).toEqual([]);

      expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1);
    } finally {
      writes?.restore();
      goSpy.mockRestore();
    }
  });

  it("allows Technical Details, Compare, and Restart on Result once a pending Back correction resolves", async () => {
    mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: previewResponse() });
    const pendingExecute = deferred<Awaited<ReturnType<typeof executeDisclosure>>>();
    mockedExecuteDisclosure.mockReturnValue(pendingExecute.promise);
    mockedCompareStrategies.mockResolvedValue({ ok: true, data: compareResponse() });
    const goSpy = vi.spyOn(window.history, "go").mockImplementation(() => {});
    let writes: ReturnType<typeof trackHistoryWrites> | null = null;
    try {
      render(<GuidedFlow />);
      const { composeId, sendingReviewId } = await reachPendingExampleSend();
      await waitFor(() => expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1));

      dispatchPopState(composeId);
      expect(goSpy).toHaveBeenCalledWith(1);

      pendingExecute.resolve({ ok: true, data: executeResponse() });
      await screen.findByRole("heading", { name: copy.result.heading });

      writes = trackHistoryWrites();

      // The corrective popstate lands: Result is registered, pushed exactly
      // once, directly after the sending Review.
      dispatchPopState(sendingReviewId);
      await waitFor(() => expect(window.history.state.flowNavigationId).not.toBe(sendingReviewId));
      const resultId = window.history.state.flowNavigationId as string;
      expect(writes.log).toEqual([`push:${resultId}`]);
      expect(goSpy).toHaveBeenCalledTimes(1);

      // From here on the correction is resolved: switch to real browser
      // navigation (matching the rest of this suite) rather than synthetic
      // popstate, so the real and tracked history stacks stay consistent.
      goSpy.mockRestore();

      // Technical Details now opens normally, and Back restores Result.
      await userEvent.click(screen.getByRole("button", { name: copy.buttons.viewTechnicalDetails }));
      await screen.findByRole("heading", { name: copy.sectionHeadings.technicalDetails });
      await userEvent.click(screen.getByRole("button", { name: copy.technicalDetails.backToResult }));
      await screen.findByRole("heading", { name: copy.result.heading });

      // Compare now calls compareStrategies and navigates to Comparison.
      await userEvent.click(screen.getByRole("button", { name: copy.buttons.compareStrategies }));
      await waitFor(() => expect(mockedCompareStrategies).toHaveBeenCalledTimes(1));
      await screen.findByRole("heading", { name: copy.comparison.heading });
      await userEvent.click(screen.getByRole("button", { name: copy.comparison.backToResult }));
      await screen.findByRole("heading", { name: copy.result.heading });

      // Restart now works normally.
      await userEvent.click(screen.getByRole("button", { name: copy.result.restart }));
      await screen.findByRole("heading", { name: copy.newTest.heading });

      expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1);
    } finally {
      writes?.restore();
      goSpy.mockRestore();
    }
  });
});

/**
 * T32.2 / #102 -- Review as a true check-before-send, built on the #101/#105
 * history machinery (snapshots, pruning, corrections) rather than beside it.
 */
const UNRECOVERABLE = "Esta etapa não pode ser restaurada";

async function startPasteReview(text: string, task: string) {
  await userEvent.click(screen.getByRole("button", { name: copy.howItWorks.ctaPrimary }));
  const composeId = window.history.state.flowNavigationId as string;
  await userEvent.click(screen.getByRole("radio", { name: copy.entryModes.pasteText }));
  await userEvent.type(screen.getByLabelText(copy.newTest.pasteLabel), text);
  await userEvent.type(screen.getByLabelText(copy.newTest.taskLabel), task);
  await userEvent.click(screen.getByRole("button", { name: copy.newTest.continueToReview }));
  await screen.findByRole("heading", { name: copy.review.heading });
  const reviewId = window.history.state.flowNavigationId as string;
  return { composeId, reviewId };
}

async function startUploadReview(file: File, task: string) {
  await userEvent.click(screen.getByRole("button", { name: copy.howItWorks.ctaPrimary }));
  const composeId = window.history.state.flowNavigationId as string;
  await userEvent.click(screen.getByRole("radio", { name: copy.entryModes.uploadFile }));
  await userEvent.upload(screen.getByLabelText(copy.newTest.uploadFieldLabel), file);
  await userEvent.type(screen.getByLabelText(copy.newTest.taskLabel), task);
  await userEvent.click(screen.getByRole("button", { name: copy.newTest.continueToReview }));
  await screen.findByRole("heading", { name: copy.review.heading });
  const reviewId = window.history.state.flowNavigationId as string;
  return { composeId, reviewId };
}

function syntheticPdf(name = "contrato-sintetico.pdf") {
  return new File([new Uint8Array([0x25, 0x50, 0x44, 0x46])], name, { type: "application/pdf" });
}

function mockTwoAnalysisModes() {
  mockedGetDocumentTypes.mockResolvedValue({
    ok: true,
    data: {
      contract_version: "t20-application-api-v1",
      document_types: [
        {
          document_type: "contract",
          analysis_modes: ["contract_summary", "financial_audit"],
          default_analysis_mode: "contract_summary",
        },
      ],
    },
  });
}

function mockTwoKnownExamples() {
  mockedGetExamples.mockResolvedValue({
    ok: true,
    data: {
      contract_version: "t20-application-api-v1",
      examples: [
        {
          example_id: "hr_team_summary_001",
          title: "hr_team_summary_001",
          domain: "hr",
          purpose: "team_summary",
          task: "Resuma a equipe.",
          character_count: 400,
        },
        {
          example_id: "hr_salary_analysis_001",
          title: "hr_salary_analysis_001",
          domain: "hr",
          purpose: "salary_analysis",
          task: "Analise os salários.",
          character_count: 400,
        },
      ],
    },
  });
}

/** A stale Review reached by Forward must be inert: fail closed, no Confirm, nothing called. */
async function expectStaleReviewIsInert(reviewId: string) {
  window.history.forward();
  expect(await screen.findByRole("heading", { name: UNRECOVERABLE })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: copy.review.confirmSend })).not.toBeInTheDocument();
  // Even an explicit popstate naming the old Review's id cannot resurrect it.
  dispatchPopState(reviewId);
  expect(screen.queryByRole("button", { name: copy.review.confirmSend })).not.toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: copy.review.heading })).not.toBeInTheDocument();
}

describe("GuidedFlow check-before-send (#102)", () => {
  it("re-presents an example's human label and the task on Review", async () => {
    mockTwoKnownExamples();
    mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: previewResponse() });
    render(<GuidedFlow />);

    await userEvent.click(screen.getByRole("button", { name: copy.howItWorks.ctaPrimary }));
    await userEvent.selectOptions(
      await screen.findByLabelText(copy.newTest.exampleFieldLabel),
      "hr_salary_analysis_001",
    );
    await userEvent.type(screen.getByLabelText(copy.newTest.taskLabel), "Compare as faixas");
    await userEvent.click(screen.getByRole("button", { name: copy.newTest.continueToReview }));
    await screen.findByRole("heading", { name: copy.review.heading });

    const context = screen.getByRole("region", { name: copy.review.contextHeading });
    expect(context).toHaveTextContent(copy.review.sourceExample);
    expect(context).toHaveTextContent(copy.examplePurposes.salary_analysis);
    expect(context).toHaveTextContent("Compare as faixas");
  });

  it("Change returns to the retained Compose entry through history with every upload field and the same File", async () => {
    mockedPreviewDocument.mockResolvedValue({
      ok: true,
      data: { ...previewResponse(), confirmation_token: "first-token" },
    });
    render(<GuidedFlow />);
    const file = syntheticPdf();
    const { composeId, reviewId } = await startUploadReview(file, "Quais são os prazos?");

    const context = screen.getByRole("region", { name: copy.review.contextHeading });
    expect(context).toHaveTextContent("contrato-sintetico.pdf");
    expect(context).toHaveTextContent(copy.newTest.documentTypeLabels.contract);
    expect(context).toHaveTextContent(copy.newTest.analysisModeLabels.contract_summary);
    expect(context).toHaveTextContent("Quais são os prazos?");

    await userEvent.click(screen.getByRole("button", { name: copy.review.changeRequest }));
    await screen.findByRole("heading", { name: copy.newTest.heading });
    // The SAME history entry (not a new one pushed by a reducer transition).
    expect(window.history.state.flowNavigationId).toBe(composeId);
    expect(screen.getByRole("radio", { name: copy.entryModes.uploadFile })).toBeChecked();
    expect(screen.getByText("contrato-sintetico.pdf")).toBeInTheDocument();
    expect(screen.getByLabelText(copy.newTest.taskLabel)).toHaveValue("Quais são os prazos?");
    expect(screen.getByLabelText(copy.newTest.documentTypeLabel)).toHaveValue("contract");

    // Nothing was edited, so Forward still reaches the same, still-valid Review.
    window.history.forward();
    await screen.findByRole("heading", { name: copy.review.heading });
    expect(window.history.state.flowNavigationId).toBe(reviewId);
    expect(mockedPreviewDocument).toHaveBeenCalledTimes(1);
    expect(mockedExecuteDocument).not.toHaveBeenCalled();

    // And a new preview from the restored Compose re-uploads the very same in-memory File.
    window.history.back();
    await screen.findByRole("heading", { name: copy.newTest.heading });
    await userEvent.click(screen.getByRole("button", { name: copy.newTest.continueToReview }));
    await screen.findByRole("heading", { name: copy.review.heading });
    expect(mockedPreviewDocument).toHaveBeenCalledTimes(2);
    const firstFile = mockedPreviewDocument.mock.calls[0][0].get("file") as File;
    const secondFile = mockedPreviewDocument.mock.calls[1][0].get("file") as File;
    expect(secondFile.name).toBe(firstFile.name);
    expect(secondFile.size).toBe(firstFile.size);
    expect(mockedExecuteDocument).not.toHaveBeenCalled();
  });

  it.each([
    [
      "the task",
      async () => {
        await userEvent.clear(screen.getByLabelText(copy.newTest.taskLabel));
        await userEvent.type(screen.getByLabelText(copy.newTest.taskLabel), "Liste apenas os prazos");
      },
      { text: "Contrato com valor R$ 125.000,00", task: "Liste apenas os prazos" },
    ],
    [
      "the pasted text",
      async () => {
        await userEvent.type(screen.getByLabelText(copy.newTest.pasteLabel), " e multa de 10%");
      },
      { text: "Contrato com valor R$ 125.000,00 e multa de 10%", task: "Resuma os riscos" },
    ],
  ])(
    "editing %s after Review invalidates the old Review; Forward cannot confirm it and a fresh preview is required",
    async (_label, edit, expectedBody) => {
      mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: previewResponse() });
      mockedExecuteDisclosure.mockResolvedValue({ ok: true, data: executeResponse() });
      render(<GuidedFlow />);
      const { reviewId } = await startPasteReview("Contrato com valor R$ 125.000,00", "Resuma os riscos");

      await userEvent.click(screen.getByRole("button", { name: copy.review.changeRequest }));
      await screen.findByRole("heading", { name: copy.newTest.heading });
      await edit();

      await expectStaleReviewIsInert(reviewId);
      expect(mockedPreviewDisclosure).toHaveBeenCalledTimes(1);
      expect(mockedExecuteDisclosure).not.toHaveBeenCalled();

      // Back to the edited Compose (edits preserved), then the only way on
      // is a new preview -- called exactly once -- and a new Confirm.
      window.history.back();
      await screen.findByRole("heading", { name: copy.newTest.heading });
      expect(mockedPreviewDisclosure).toHaveBeenCalledTimes(1);
      await userEvent.click(screen.getByRole("button", { name: copy.newTest.continueToReview }));
      await screen.findByRole("heading", { name: copy.review.heading });
      expect(mockedPreviewDisclosure).toHaveBeenCalledTimes(2);
      expect(mockedPreviewDisclosure.mock.calls[1][0]).toEqual(expectedBody);
      expect(mockedExecuteDisclosure).not.toHaveBeenCalled();

      await userEvent.click(screen.getByRole("button", { name: copy.review.confirmSend }));
      await screen.findByRole("heading", { name: copy.result.heading });
      expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1);
      expect(mockedExecuteDisclosure.mock.calls[0][0]).toEqual(expectedBody);
    },
  );

  it("switching the entry mode after Review invalidates the old Review", async () => {
    mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: previewResponse() });
    render(<GuidedFlow />);
    const { reviewId } = await startPasteReview("Contrato com valor R$ 125.000,00", "Resuma os riscos");

    await userEvent.click(screen.getByRole("button", { name: copy.review.changeRequest }));
    await screen.findByRole("heading", { name: copy.newTest.heading });
    await userEvent.click(screen.getByRole("radio", { name: copy.entryModes.useExample }));

    await expectStaleReviewIsInert(reviewId);
    expect(mockedPreviewDisclosure).toHaveBeenCalledTimes(1);
    expect(mockedExecuteDisclosure).not.toHaveBeenCalled();
  });

  it("choosing a different example after Review invalidates the old Review", async () => {
    mockTwoKnownExamples();
    mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: previewResponse() });
    render(<GuidedFlow />);
    await userEvent.click(screen.getByRole("button", { name: copy.howItWorks.ctaPrimary }));
    await userEvent.selectOptions(
      await screen.findByLabelText(copy.newTest.exampleFieldLabel),
      "hr_team_summary_001",
    );
    await userEvent.click(screen.getByRole("button", { name: copy.newTest.continueToReview }));
    await screen.findByRole("heading", { name: copy.review.heading });
    const reviewId = window.history.state.flowNavigationId as string;

    window.history.back();
    await screen.findByRole("heading", { name: copy.newTest.heading });
    await userEvent.selectOptions(
      screen.getByLabelText(copy.newTest.exampleFieldLabel),
      "hr_salary_analysis_001",
    );

    await expectStaleReviewIsInert(reviewId);
    expect(mockedPreviewDisclosure).toHaveBeenCalledTimes(1);
    expect(mockedExecuteDisclosure).not.toHaveBeenCalled();
  });

  it("changing the upload's analysis type after Review invalidates the old Review and its token; only the fresh token is ever sent", async () => {
    mockTwoAnalysisModes();
    mockedPreviewDocument
      .mockResolvedValueOnce({ ok: true, data: { ...previewResponse(), confirmation_token: "first-token" } })
      .mockResolvedValueOnce({ ok: true, data: { ...previewResponse(), confirmation_token: "second-token" } });
    mockedExecuteDocument.mockResolvedValue({ ok: true, data: executeResponse() });
    render(<GuidedFlow />);
    const { reviewId } = await startUploadReview(syntheticPdf(), "Quais são os prazos?");

    await userEvent.click(screen.getByRole("button", { name: copy.review.changeRequest }));
    await screen.findByRole("heading", { name: copy.newTest.heading });
    await userEvent.selectOptions(screen.getByLabelText(copy.newTest.analysisModeLabel), "financial_audit");

    await expectStaleReviewIsInert(reviewId);
    expect(mockedExecuteDocument).not.toHaveBeenCalled();

    window.history.back();
    await screen.findByRole("heading", { name: copy.newTest.heading });
    await userEvent.click(screen.getByRole("button", { name: copy.newTest.continueToReview }));
    await screen.findByRole("heading", { name: copy.review.heading });
    expect(mockedPreviewDocument).toHaveBeenCalledTimes(2);
    expect(mockedPreviewDocument.mock.calls[1][0].get("analysis_mode")).toBe("financial_audit");
    expect(mockedExecuteDocument).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: copy.review.confirmSend }));
    await screen.findByRole("heading", { name: copy.result.heading });
    expect(mockedExecuteDocument).toHaveBeenCalledTimes(1);
    expect(mockedExecuteDocument.mock.calls[0][0].get("confirmation_token")).toBe("second-token");
    expect(mockedExecuteDocument.mock.calls[0][0].get("analysis_mode")).toBe("financial_audit");
  });

  it("removing the uploaded file after Review invalidates the old Review", async () => {
    mockedPreviewDocument.mockResolvedValue({
      ok: true,
      data: { ...previewResponse(), confirmation_token: "first-token" },
    });
    render(<GuidedFlow />);
    const { reviewId } = await startUploadReview(syntheticPdf(), "Quais são os prazos?");

    window.history.back();
    await screen.findByRole("heading", { name: copy.newTest.heading });
    await userEvent.click(screen.getByRole("button", { name: copy.newTest.removeFile }));

    await expectStaleReviewIsInert(reviewId);
    expect(mockedExecuteDocument).not.toHaveBeenCalled();
  });

  it("shows the Approved Review with its context after Result -> Back, and returns to Result without replay", async () => {
    mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: previewResponse() });
    mockedExecuteDisclosure.mockResolvedValue({ ok: true, data: executeResponse() });
    render(<GuidedFlow />);
    await startPasteReview("Contrato com valor R$ 125.000,00", "Resuma os riscos");
    await userEvent.click(screen.getByRole("button", { name: copy.review.confirmSend }));
    await screen.findByRole("heading", { name: copy.result.heading });
    const resultId = window.history.state.flowNavigationId as string;

    window.history.back();
    await expectApprovedReview();
    const context = screen.getByRole("region", { name: copy.review.contextHeading });
    expect(context).toHaveTextContent(copy.review.sourcePaste);
    expect(context).toHaveTextContent("Resuma os riscos");
    expect(screen.getByText(copy.approvedReview.sentHeading)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: copy.approvedReview.goToResult }));
    await screen.findByRole("heading", { name: copy.result.heading });
    expect(window.history.state.flowNavigationId).toBe(resultId);

    window.history.back();
    await expectApprovedReview();
    window.history.forward();
    await screen.findByRole("heading", { name: copy.result.heading });

    expect(mockedPreviewDisclosure).toHaveBeenCalledTimes(1);
    expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1);
    expect(mockedCompareStrategies).not.toHaveBeenCalled();
  });

  it("keeps the confirmation token out of the Approved Review snapshot, history state, URL and storage", async () => {
    const token = "opaque.confirmation.token-XYZ";
    mockedPreviewDocument.mockResolvedValue({ ok: true, data: { ...previewResponse(), confirmation_token: token } });
    mockedExecuteDocument.mockResolvedValue({ ok: true, data: executeResponse() });
    const tracker = trackRetainedFlowSnapshots();
    try {
      render(<GuidedFlow />);
      const { reviewId } = await startUploadReview(syntheticPdf("segredo-cliente.pdf"), "Tarefa sigilosa");
      await userEvent.click(screen.getByRole("button", { name: copy.review.confirmSend }));
      await screen.findByRole("heading", { name: copy.result.heading });

      const approved = tracker.lastValue(reviewId) as Record<string, unknown>;
      expect(approved.screen).toBe("approvedReview");
      expect(approved).not.toHaveProperty("confirmationToken");
      expect(JSON.stringify(approved)).not.toContain(token);

      window.history.back();
      await expectApprovedReview();
      expect(document.body.textContent).not.toContain(token);
      for (const channel of [JSON.stringify(window.history.state), window.location.href]) {
        expect(channel).not.toContain(token);
        expect(channel).not.toContain("segredo-cliente");
        expect(channel).not.toContain("Tarefa sigilosa");
      }
      expect(window.localStorage.length).toBe(0);
      expect(window.sessionStorage.length).toBe(0);
      expect(mockedExecuteDocument).toHaveBeenCalledTimes(1);
    } finally {
      tracker.restore();
    }
  });

  it("from the Approved Review, Back to the historical Compose calls nothing; a new send needs preview, Review and Confirm", async () => {
    mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: previewResponse() });
    mockedExecuteDisclosure.mockResolvedValue({ ok: true, data: executeResponse() });
    render(<GuidedFlow />);
    await startPasteReview("Contrato com valor R$ 125.000,00", "Resuma os riscos");
    await userEvent.click(screen.getByRole("button", { name: copy.review.confirmSend }));
    await screen.findByRole("heading", { name: copy.result.heading });

    window.history.back();
    await expectApprovedReview();
    await userEvent.click(screen.getByRole("button", { name: "Voltar" }));
    await screen.findByRole("heading", { name: copy.newTest.heading });
    expect(screen.getByLabelText(copy.newTest.taskLabel)).toHaveValue("Resuma os riscos");
    expect(mockedPreviewDisclosure).toHaveBeenCalledTimes(1);
    expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1);

    await userEvent.click(screen.getByRole("button", { name: copy.newTest.continueToReview }));
    await screen.findByRole("heading", { name: copy.review.heading });
    expect(mockedPreviewDisclosure).toHaveBeenCalledTimes(2);
    expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1);
    await userEvent.click(screen.getByRole("button", { name: copy.review.confirmSend }));
    await screen.findByRole("heading", { name: copy.result.heading });
    expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(2);
  });

  it("a provider failure keeps the live Review with its context; Back/Forward never re-executes and a retry needs an explicit Confirm", async () => {
    mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: previewResponse() });
    mockedExecuteDisclosure
      .mockResolvedValueOnce({
        ok: false,
        status: 502,
        error: { message: copy.errors.upstreamUnreachable, kind: null, fields: null },
      })
      .mockResolvedValueOnce({ ok: true, data: executeResponse() });
    render(<GuidedFlow />);
    await startPasteReview("Contrato com valor R$ 125.000,00", "Resuma os riscos");
    await userEvent.click(screen.getByRole("button", { name: copy.review.confirmSend }));

    expect(await screen.findByRole("alert")).toHaveTextContent(copy.errors.upstreamUnreachable);
    expect(screen.getByText(copy.review.executeErrorNoAutoRetry)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: copy.review.heading })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: copy.review.contextHeading })).toHaveTextContent("Resuma os riscos");
    // A failed execute is NOT an approved send.
    expect(screen.queryByRole("heading", { name: copy.approvedReview.heading })).not.toBeInTheDocument();
    expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1);

    window.history.back();
    await screen.findByRole("heading", { name: copy.newTest.heading });
    window.history.forward();
    await screen.findByRole("heading", { name: copy.review.heading });
    expect(screen.queryByRole("heading", { name: copy.approvedReview.heading })).not.toBeInTheDocument();
    expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1);

    await userEvent.click(screen.getByRole("button", { name: copy.review.confirmSend }));
    await screen.findByRole("heading", { name: copy.result.heading });
    expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(2);
    expect(mockedPreviewDisclosure).toHaveBeenCalledTimes(1);
  });

  it("an expired confirmation returns to Compose with fields kept, and the expired Review can never be confirmed again", async () => {
    mockedPreviewDocument
      .mockResolvedValueOnce({ ok: true, data: { ...previewResponse(), confirmation_token: "expired-token" } })
      .mockResolvedValueOnce({ ok: true, data: { ...previewResponse(), confirmation_token: "fresh-token" } });
    mockedExecuteDocument
      .mockResolvedValueOnce({
        ok: false,
        status: 409,
        error: { message: copy.errors.previewExpired, kind: "PreviewConfirmationError", fields: null },
      })
      .mockResolvedValueOnce({ ok: true, data: executeResponse() });
    render(<GuidedFlow />);
    await startUploadReview(syntheticPdf(), "Quais são os prazos?");
    await userEvent.click(screen.getByRole("button", { name: copy.review.confirmSend }));

    await screen.findByRole("heading", { name: copy.newTest.heading });
    expect(screen.getByRole("alert")).toHaveTextContent(copy.errors.previewExpired);
    expect(screen.getByText("contrato-sintetico.pdf")).toBeInTheDocument();
    expect(screen.getByLabelText(copy.newTest.taskLabel)).toHaveValue("Quais são os prazos?");
    expect(mockedExecuteDocument).toHaveBeenCalledTimes(1);

    // Browser Back lands on the expired Review's entry: fail closed.
    window.history.back();
    expect(await screen.findByRole("heading", { name: UNRECOVERABLE })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: copy.review.confirmSend })).not.toBeInTheDocument();
    expect(mockedExecuteDocument).toHaveBeenCalledTimes(1);

    window.history.forward();
    await screen.findByRole("heading", { name: copy.newTest.heading });
    await userEvent.click(screen.getByRole("button", { name: copy.newTest.continueToReview }));
    await screen.findByRole("heading", { name: copy.review.heading });
    expect(mockedPreviewDocument).toHaveBeenCalledTimes(2);
    await userEvent.click(screen.getByRole("button", { name: copy.review.confirmSend }));
    await screen.findByRole("heading", { name: copy.result.heading });
    expect(mockedExecuteDocument).toHaveBeenCalledTimes(2);
    expect(mockedExecuteDocument.mock.calls[1][0].get("confirmation_token")).toBe("fresh-token");
  });

  it("a preview failure returns to Compose with every field preserved", async () => {
    mockedPreviewDisclosure.mockResolvedValue({
      ok: false,
      status: 422,
      error: { message: copy.errors.validationFailed, kind: null, fields: null },
    });
    render(<GuidedFlow />);
    await userEvent.click(screen.getByRole("button", { name: copy.howItWorks.ctaPrimary }));
    await userEvent.click(screen.getByRole("radio", { name: copy.entryModes.pasteText }));
    await userEvent.type(screen.getByLabelText(copy.newTest.pasteLabel), "Texto a revisar");
    await userEvent.type(screen.getByLabelText(copy.newTest.taskLabel), "Resuma");
    await userEvent.click(screen.getByRole("button", { name: copy.newTest.continueToReview }));

    expect(await screen.findByRole("alert")).toHaveTextContent(copy.errors.validationFailed);
    expect(screen.getByLabelText(copy.newTest.pasteLabel)).toHaveValue("Texto a revisar");
    expect(screen.getByLabelText(copy.newTest.taskLabel)).toHaveValue("Resuma");
    expect(mockedExecuteDisclosure).not.toHaveBeenCalled();
  });

  it("preview processing shows one honest message, not a fabricated sequence of sub-stages", async () => {
    const pendingPreview = deferred<Awaited<ReturnType<typeof previewDisclosure>>>();
    mockedPreviewDisclosure.mockReturnValue(pendingPreview.promise);
    render(<GuidedFlow />);
    await userEvent.click(screen.getByRole("button", { name: copy.howItWorks.ctaPrimary }));
    await userEvent.selectOptions(await screen.findByLabelText(copy.newTest.exampleFieldLabel), "ex-1");
    await userEvent.click(screen.getByRole("button", { name: copy.newTest.continueToReview }));

    const status = await screen.findByRole("status");
    expect(status.textContent?.trim()).toBe(copy.processingStages.preparingReview);
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/Detectando dados sensíveis|Aplicando política/);

    pendingPreview.resolve({ ok: true, data: previewResponse() });
    await screen.findByRole("heading", { name: copy.review.heading });
  });

  it("document preview processing names the document once, with no sub-stage list", async () => {
    const pendingPreview = deferred<Awaited<ReturnType<typeof previewDocument>>>();
    mockedPreviewDocument.mockReturnValue(pendingPreview.promise);
    render(<GuidedFlow />);
    await userEvent.click(screen.getByRole("button", { name: copy.howItWorks.ctaPrimary }));
    await userEvent.click(screen.getByRole("radio", { name: copy.entryModes.uploadFile }));
    await userEvent.upload(screen.getByLabelText(copy.newTest.uploadFieldLabel), syntheticPdf());
    await userEvent.type(screen.getByLabelText(copy.newTest.taskLabel), "Resuma");
    await userEvent.click(screen.getByRole("button", { name: copy.newTest.continueToReview }));

    const status = await screen.findByRole("status");
    expect(status.textContent?.trim()).toBe(copy.processingStages.preparingDocumentReview);
    expect(document.body.textContent).not.toMatch(/Lendo o arquivo|Analisando o documento/);
    pendingPreview.resolve({ ok: true, data: { ...previewResponse(), confirmation_token: "t" } });
    await screen.findByRole("heading", { name: copy.review.heading });
  });

  it("execute processing says the send was confirmed and that leaving does not cancel it -- no fake progress", async () => {
    mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: previewResponse() });
    const pendingExecute = deferred<Awaited<ReturnType<typeof executeDisclosure>>>();
    mockedExecuteDisclosure.mockReturnValue(pendingExecute.promise);
    render(<GuidedFlow />);
    await reachPendingExampleSend();

    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent(copy.processingStages.sendConfirmed);
    expect(status).toHaveTextContent(copy.processingStages.leavingDoesNotCancel);
    expect(status.querySelectorAll("p")).toHaveLength(2);
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/Consultando o modelo|Reconstruindo a resposta/);

    pendingExecute.resolve({ ok: true, data: executeResponse() });
    await screen.findByRole("heading", { name: copy.result.heading });
  });
});
