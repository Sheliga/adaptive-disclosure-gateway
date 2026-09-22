import { render, screen, waitFor } from "@testing-library/react";
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
    restore: () => {
      mapSet.mockRestore();
      mapDelete.mockRestore();
    },
  };
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

    window.history.back();
    await screen.findByRole("heading", { name: "Esta etapa não pode ser restaurada" });
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

  it("does not restore executing after a pending send resolves or offer resend through browser Back", async () => {
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

    pendingExecute.resolve({ ok: true, data: executeResponse() });
    await screen.findByRole("heading", { name: copy.result.heading });
    window.history.back();

    expect(await screen.findByRole("heading", { name: "Esta etapa não pode ser restaurada" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: copy.review.confirmSend })).not.toBeInTheDocument();
    expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1);
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

    expect(await screen.findByRole("heading", { name: "Esta etapa não pode ser restaurada" })).toBeInTheDocument();
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

  it("does not retain the Result snapshot after backing into an unrecoverable send and starting a new flow", async () => {
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
    // Review entry, which is unrecoverable.
    window.history.back();
    expect(
      await screen.findByRole("heading", { name: "Esta etapa não pode ser restaurada" }),
    ).toBeInTheDocument();

    // Start an entirely new flow from there -- the only affordance the
    // unrecoverable screen offers.
    await userEvent.click(screen.getByRole("button", { name: "Voltar à introdução" }));
    await screen.findByRole("heading", { name: copy.howItWorks.title });
    await userEvent.click(screen.getByRole("button", { name: copy.howItWorks.ctaPrimary }));
    await userEvent.selectOptions(await screen.findByLabelText(copy.newTest.exampleFieldLabel), "ex-1");
    await userEvent.click(screen.getByRole("button", { name: copy.newTest.continueToReview }));
    await screen.findByRole("heading", { name: copy.review.heading });

    // The abandoned Result entry (which carries the execute payload) must
    // not still be retained once a new branch has been pushed.
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
    // the comment above `goSpy`): its snapshot was dropped the moment the
    // send succeeded, so it must now read as unrecoverable.
    window.dispatchEvent(
      new PopStateEvent("popstate", { state: { flowNavigationId: sendingReviewId } }),
    );
    expect(
      await screen.findByRole("heading", { name: "Esta etapa não pode ser restaurada" }),
    ).toBeInTheDocument();
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
    // same determinism reason as above: its snapshot was dropped the moment
    // the send succeeded, so it must now read as unrecoverable.
    window.dispatchEvent(
      new PopStateEvent("popstate", { state: { flowNavigationId: sendingReviewId } }),
    );
    expect(await screen.findByRole("heading", { name: "Esta etapa não pode ser restaurada" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: copy.newTest.heading })).not.toBeInTheDocument();
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

    expect(await screen.findByRole("heading", { name: "Esta etapa não pode ser restaurada" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: copy.review.confirmSend })).not.toBeInTheDocument();
    expect(mockedPreviewDisclosure).toHaveBeenCalledTimes(1);
    expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1);
    expect(mockedCompareStrategies).not.toHaveBeenCalled();
  });
});
