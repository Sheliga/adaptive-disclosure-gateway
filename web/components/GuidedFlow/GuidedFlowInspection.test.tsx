/**
 * T32.3 / #103 -- the three demo capabilities through the real GuidedFlow:
 * the before/after appears only for INSPECTION, export/restore only for
 * TRANSPARENCY, the Vault Explorer only for VAULT_EXPLORER, and a failed
 * features fetch leaves every optional surface off. Also pins the Approved
 * Review / Result behavior and that segment values never reach the URL,
 * history state, Web Storage or the console.
 */

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resetVolatileLocaleForTests } from "@/i18n/LocaleProvider";
import {
  compareStrategies,
  executeDisclosure,
  executeDocument,
  getDemoFeatures,
  getDocumentTypes,
  getExamples,
  getHealth,
  previewDisclosure,
  previewDocument,
} from "@/lib/api";
import type { DisclosureInspection, ExecuteResponse, HealthResponse, PreviewResponse } from "@/lib/contracts";
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

/** Values that only ever exist inside the preview's inspection segments. */
const ORIGINAL_NAME = "SENTINELA-ORIGINAL-Maria-Q7";
const PSEUDONYM = "SENTINELA-PSEUDONIMO-P9";
const ORIGINAL_CPF = "SENTINELA-CPF-111.222.333-44";

function inspection(name = ORIGINAL_NAME, pseudonym = PSEUDONYM): DisclosureInspection {
  return {
    available: true,
    unavailable_reason: null,
    segments: [
      { action: null, category: null, original: "Contrato de ", disclosed: "Contrato de " },
      { action: "pseudonymize", category: "employee_name", original: name, disclosed: pseudonym },
      { action: null, category: null, original: ", CPF ", disclosed: ", CPF " },
      { action: "remove", category: "cpf", original: ORIGINAL_CPF, disclosed: "" },
    ],
  };
}

function previewResponse(insp: DisclosureInspection | null = inspection()): PreviewResponse {
  const payload = insp && insp.available ? insp.segments.map((s) => s.disclosed).join("") : "payload";
  return {
    contract_version: "t20-application-api-v1",
    summary: { status: "allowed", categories: [], detected_span_count: 2, detected_categories: [] },
    external_payload: payload,
    payload_byte_count: payload.length,
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
    inspection: insp,
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
    reconstruction: { attempted: true, reconstructed_hash: "hash2", changed_from_provider_response: false },
    treatment: "b4",
    strategy: "recommended",
    governance: previewResponse().governance,
    total_ms: 100,
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

function features(inspectionOn: boolean, transparencyOn: boolean, vaultOn: boolean) {
  mockedGetDemoFeatures.mockResolvedValue({
    ok: true,
    data: {
      demo_inspection_enabled: inspectionOn,
      demo_transparency_enabled: transparencyOn,
      demo_vault_explorer_enabled: vaultOn,
    },
  });
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

async function startPasteReview(text = "Contrato de Maria, CPF 111", task = "Resuma o contrato") {
  await userEvent.click(screen.getByRole("button", { name: copy.howItWorks.ctaPrimary }));
  await userEvent.click(screen.getByRole("radio", { name: copy.entryModes.pasteText }));
  await userEvent.type(screen.getByLabelText(copy.newTest.pasteLabel), text);
  await userEvent.type(screen.getByLabelText(copy.newTest.taskLabel), task);
  await userEvent.click(screen.getByRole("button", { name: copy.newTest.continueToReview }));
  await screen.findByRole("heading", { name: copy.review.heading });
}

/** Features resolve on mount; wait for that before asserting on flag-gated UI. */
async function renderFlow() {
  render(<GuidedFlow />);
  await vi.waitFor(() => expect(mockedGetDemoFeatures).toHaveBeenCalled());
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
    data: { contract_version: "t20-application-api-v1", examples: [] },
  });
  mockedGetDocumentTypes.mockResolvedValue({
    ok: true,
    data: { contract_version: "t20-application-api-v1", document_types: [] },
  });
  features(false, false, false);
  mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: previewResponse() });
  mockedExecuteDisclosure.mockResolvedValue({ ok: true, data: executeResponse() });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("GuidedFlow -- capability matrix (T32.3 / #103)", () => {
  it("(0,0,0): no before/after, no technical tools, no recap", async () => {
    await renderFlow();
    await startPasteReview();

    expect(screen.queryByTestId("before-after-summary")).not.toBeInTheDocument();
    expect(screen.queryByText(copy.review.technicalToolsToggle)).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain(ORIGINAL_NAME);

    await userEvent.click(screen.getByRole("button", { name: copy.review.confirmSend }));
    await screen.findByRole("heading", { name: copy.result.heading });
    expect(screen.queryByTestId("result-recap")).not.toBeInTheDocument();
    expect(screen.queryByText(copy.vaultExplorerPanel.toggleLabel)).not.toBeInTheDocument();
  });

  it("(1,0,0) public posture: before/after and recap shown; no export/restore and no Vault Explorer anywhere", async () => {
    features(true, false, false);
    await renderFlow();
    await startPasteReview();

    const summary = screen.getByTestId("before-after-summary");
    expect(within(summary).getByText(ORIGINAL_NAME)).toBeInTheDocument();
    expect(within(summary).getByText(PSEUDONYM)).toBeInTheDocument();
    expect(screen.queryByText(copy.review.technicalToolsToggle)).not.toBeInTheDocument();
    expect(screen.queryByText(copy.exportRestorePanel.exportButton)).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: copy.review.confirmSend }));
    await screen.findByRole("heading", { name: copy.result.heading });
    const recap = screen.getByTestId("result-recap");
    expect(within(recap).getByText(copy.resultRecap.handledCount.replace("{n}", "2"))).toBeInTheDocument();
    expect(screen.queryByText(copy.vaultExplorerPanel.toggleLabel)).not.toBeInTheDocument();
    expect(mockedPreviewDisclosure).toHaveBeenCalledTimes(1);
    expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1);
  });

  it("(0,1,0): transparency never implies the before/after or the recap, but keeps its own tools", async () => {
    features(false, true, false);
    await renderFlow();
    await startPasteReview();

    expect(screen.queryByTestId("before-after-summary")).not.toBeInTheDocument();
    expect(screen.queryByText(copy.review.understandChangesToggle)).not.toBeInTheDocument();
    expect(screen.getByText(copy.review.technicalToolsToggle)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: copy.review.confirmSend }));
    await screen.findByRole("heading", { name: copy.result.heading });
    expect(screen.queryByTestId("result-recap")).not.toBeInTheDocument();
  });

  it("(0,0,1): the vault explorer never implies the before/after", async () => {
    features(false, false, true);
    await renderFlow();
    await startPasteReview();

    expect(screen.queryByTestId("before-after-summary")).not.toBeInTheDocument();
    expect(screen.getByText(copy.review.technicalToolsToggle)).toBeInTheDocument();
  });

  it("a failed features fetch turns every optional capability off", async () => {
    mockedGetDemoFeatures.mockResolvedValue({ ok: false, error: { kind: "network", message: "x" } } as never);
    await renderFlow();
    await startPasteReview();

    expect(screen.queryByTestId("before-after-summary")).not.toBeInTheDocument();
    expect(screen.queryByText(copy.review.technicalToolsToggle)).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain(ORIGINAL_NAME);
  });
});

describe("GuidedFlow -- Approved Review and Result with inspection (T32.3 / #103)", () => {
  it("Review -> Confirm -> Result -> Back shows the approved before/after, read-only, with no replayed call", async () => {
    features(true, false, false);
    await renderFlow();
    await startPasteReview();
    await userEvent.click(screen.getByRole("button", { name: copy.review.confirmSend }));
    await screen.findByRole("heading", { name: copy.result.heading });
    const resultId = window.history.state.flowNavigationId as string;

    window.history.back();
    expect(await screen.findByRole("heading", { name: copy.approvedReview.heading })).toBeInTheDocument();
    const summary = screen.getByTestId("before-after-summary");
    expect(within(summary).getByText(copy.beforeAfter.disclosedHeadingApproved)).toBeInTheDocument();
    expect(within(summary).getByText(PSEUDONYM)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: copy.review.confirmSend })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: copy.review.changeRequest })).not.toBeInTheDocument();
    expect(screen.queryByText(copy.review.technicalToolsToggle)).not.toBeInTheDocument();

    window.history.forward();
    await screen.findByRole("heading", { name: copy.result.heading });
    expect(window.history.state.flowNavigationId).toBe(resultId);
    expect(screen.getByTestId("result-recap")).toBeInTheDocument();

    expect(mockedPreviewDisclosure).toHaveBeenCalledTimes(1);
    expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1);
    expect(mockedCompareStrategies).not.toHaveBeenCalled();
    expect(mockedPreviewDocument).not.toHaveBeenCalled();
    expect(mockedExecuteDocument).not.toHaveBeenCalled();
  });

  it("an edit after Review shows only the fresh preview's before/after, never the stale one", async () => {
    features(true, false, false);
    mockedPreviewDisclosure
      .mockResolvedValueOnce({ ok: true, data: previewResponse(inspection("NOME-ANTIGO-A1", "PSEUDO-ANTIGO")) })
      .mockResolvedValueOnce({ ok: true, data: previewResponse(inspection("NOME-NOVO-B2", "PSEUDO-NOVO")) });
    await renderFlow();
    await startPasteReview();
    expect(screen.getByText("NOME-ANTIGO-A1")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: copy.review.changeRequest }));
    await screen.findByRole("heading", { name: copy.newTest.heading });
    await userEvent.type(screen.getByLabelText(copy.newTest.pasteLabel), " editado");
    await userEvent.click(screen.getByRole("button", { name: copy.newTest.continueToReview }));
    await screen.findByRole("heading", { name: copy.review.heading });

    expect(screen.getByText("NOME-NOVO-B2")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("NOME-ANTIGO-A1");
    expect(document.body.textContent).not.toContain("PSEUDO-ANTIGO");
    expect(mockedPreviewDisclosure).toHaveBeenCalledTimes(2);
    expect(mockedExecuteDisclosure).not.toHaveBeenCalled();
  });
});

describe("GuidedFlow -- inspection values never leave the in-memory flow (T32.3 / #103)", () => {
  it("keeps originals and pseudonyms out of the URL, history state, Web Storage and the console", async () => {
    features(true, false, false);
    const consoleSpies = (["log", "info", "warn", "error", "debug"] as const).map((method) =>
      vi.spyOn(console, method).mockImplementation(() => undefined),
    );
    const channels: string[] = [];
    const snapshot = () => {
      channels.push(window.location.href, JSON.stringify(window.history.state));
      for (const storage of [window.localStorage, window.sessionStorage]) {
        for (let i = 0; i < storage.length; i += 1) {
          const key = storage.key(i) ?? "";
          channels.push(key, storage.getItem(key) ?? "");
        }
      }
    };

    await renderFlow();
    await startPasteReview();
    expect(screen.getByText(ORIGINAL_NAME)).toBeInTheDocument();
    snapshot();
    await userEvent.click(screen.getByRole("button", { name: copy.review.confirmSend }));
    await screen.findByRole("heading", { name: copy.result.heading });
    snapshot();
    window.history.back();
    await screen.findByRole("heading", { name: copy.approvedReview.heading });
    snapshot();
    window.history.forward();
    await screen.findByRole("heading", { name: copy.result.heading });
    snapshot();

    for (const value of [ORIGINAL_NAME, PSEUDONYM, ORIGINAL_CPF]) {
      for (const channel of channels) {
        expect(channel).not.toContain(value);
      }
      for (const spy of consoleSpies) {
        expect(JSON.stringify(spy.mock.calls)).not.toContain(value);
      }
    }
    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.length).toBe(0);
  });
});
