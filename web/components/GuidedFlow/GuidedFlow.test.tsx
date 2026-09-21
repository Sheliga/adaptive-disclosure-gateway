import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { resetVolatileLocaleForTests } from "@/i18n/LocaleProvider";
import { readStoredLocale } from "@/i18n/localeStorage";
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
import type { CompareResponse, DocumentPreviewResponse, ExecuteResponse, HealthResponse, PreviewResponse } from "@/lib/contracts";
import { copy } from "@/lib/copy";
import { en } from "@/lib/copy.en";

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

function healthResponse(deterministicDemoMode = true): HealthResponse {
  return {
    status: "ok",
    contract_version: "t20-application-api-v1",
    provider: {
      provider_class: "FakeProvider",
      model_id: "fake-1",
      model_snapshot: "2026-01-01",
      deterministic_demo_mode: deterministicDemoMode,
    },
    treatments_available: ["b0", "b1", "b2", "b3", "b4"],
  };
}

function previewResponse(): PreviewResponse {
  return {
    contract_version: "t20-application-api-v1",
    summary: {
      status: "allowed",
      categories: [
        {
          category: "email",
          outcome: "pseudonymized",
          action: "pseudonymize",
          crosses_trust_boundary: true,
          occurrence_count: 1,
          required_for_task: null,
          technical_reason: "detected by rule X",
          policy_version: "v1",
          policy_restricted: null,
          impossible_under_policy: null,
        },
      ],
      detected_span_count: 1,
      detected_categories: ["email"],
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
    final_answer: "Resposta final reconstruída localmente.",
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
    governance: {
      domain: "demo",
      purpose: "demo",
      policy_version: "v1",
      provider_class: "FakeProvider",
      requester_role: null,
      requested_pseudonym_scope: "session",
    },
    total_ms: 100,
  };
}

function compareResponse(): CompareResponse {
  return {
    contract_version: "t20-application-api-v1",
    entries: [
      {
        strategy: "b0",
        treatment: "b0",
        recommended: false,
        unsafe_control_baseline: true,
        summary: previewResponse().summary,
        external_payload: "conteudo original sem protecao",
        payload_byte_count: 30,
      },
      {
        strategy: "b1",
        treatment: "b1",
        recommended: false,
        unsafe_control_baseline: false,
        summary: previewResponse().summary,
        external_payload: "conteudo b1",
        payload_byte_count: 12,
      },
      {
        strategy: "b2",
        treatment: "b2",
        recommended: false,
        unsafe_control_baseline: false,
        summary: previewResponse().summary,
        external_payload: "conteudo b2",
        payload_byte_count: 12,
      },
      {
        strategy: "b3",
        treatment: "b3",
        recommended: false,
        unsafe_control_baseline: false,
        summary: previewResponse().summary,
        external_payload: "conteudo b3",
        payload_byte_count: 12,
      },
      {
        strategy: "b4",
        treatment: "b4",
        recommended: true,
        unsafe_control_baseline: false,
        summary: previewResponse().summary,
        external_payload: "conteudo transformado",
        payload_byte_count: 22,
      },
    ],
    governance: previewResponse().governance,
    provider_mode: { provider_class: "FakeProvider" },
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
  window.localStorage.clear();
  resetVolatileLocaleForTests();
  document.documentElement.removeAttribute("data-theme");
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
          analysis_modes: ["contract_summary", "financial_audit", "compliance_review"],
          default_analysis_mode: "contract_summary",
        },
      ],
    },
  });
  // Disabled by default -- every existing test in this file that never
  // overrides this mock is exactly the "features disabled" regression test
  // for T28's gating.
  mockedGetDemoFeatures.mockResolvedValue({ ok: true, data: { demo_transparency_enabled: false, demo_vault_explorer_enabled: false } });
});

describe("GuidedFlow -- confirmed structured contract flow", () => {
  it("uploads the same PDF twice and executes only after explicit review confirmation", async () => {
    const consoleLog = vi.spyOn(console, "log").mockImplementation(() => {});
    const documentPreview: DocumentPreviewResponse = {
      ...previewResponse(),
      confirmation_token: "opaque.confirmation.token",
    };
    mockedPreviewDocument.mockResolvedValue({ ok: true, data: documentPreview });
    mockedExecuteDocument.mockResolvedValue({ ok: true, data: executeResponse() });

    render(<GuidedFlow />);
    await userEvent.click(screen.getByRole("button", { name: copy.howItWorks.ctaPrimary }));
    await userEvent.click(screen.getByRole("radio", { name: copy.entryModes.uploadFile }));

    const file = new File([new Uint8Array([0x25, 0x50, 0x44, 0x46])], "synthetic-contract.pdf", {
      type: "application/pdf",
    });
    await userEvent.upload(screen.getByLabelText(copy.newTest.uploadFieldLabel), file);
    await userEvent.type(
      screen.getByLabelText(copy.newTest.taskLabel),
      "Quais são as principais obrigações e prazos?",
    );
    await userEvent.click(screen.getByRole("button", { name: copy.newTest.continueToReview }));

    await screen.findByRole("heading", { name: copy.review.heading });
    expect(mockedPreviewDocument).toHaveBeenCalledTimes(1);
    expect(mockedExecuteDocument).not.toHaveBeenCalled();
    expect(document.body).not.toHaveTextContent("opaque.confirmation.token");
    expect(JSON.stringify(consoleLog.mock.calls)).not.toContain("opaque.confirmation.token");
    expect(Object.values(window.localStorage)).not.toContain("opaque.confirmation.token");

    const previewForm = mockedPreviewDocument.mock.calls[0][0];
    expect(previewForm.get("file")).toBe(file);
    expect(previewForm.get("document_type")).toBe("contract");
    expect(previewForm.get("analysis_mode")).toBe("contract_summary");

    await userEvent.click(screen.getByRole("button", { name: copy.review.confirmSend }));
    await screen.findByRole("heading", { name: copy.result.heading });

    const executeForm = mockedExecuteDocument.mock.calls[0][0];
    expect(executeForm.get("file")).toBe(file);
    expect(executeForm.get("task")).toBe(previewForm.get("task"));
    expect(executeForm.get("document_type")).toBe(previewForm.get("document_type"));
    expect(executeForm.get("analysis_mode")).toBe(previewForm.get("analysis_mode"));
    expect(executeForm.get("confirmation_token")).toBe("opaque.confirmation.token");
    expect(document.body).not.toHaveTextContent("opaque.confirmation.token");
  });

  it("cancelling, editing, and submitting again requires a new preview token", async () => {
    mockedPreviewDocument
      .mockResolvedValueOnce({
        ok: true,
        data: { ...previewResponse(), confirmation_token: "first-token" },
      })
      .mockResolvedValueOnce({
        ok: true,
        data: { ...previewResponse(), confirmation_token: "second-token" },
      });
    mockedExecuteDocument.mockResolvedValue({ ok: true, data: executeResponse() });

    render(<GuidedFlow />);
    await userEvent.click(screen.getByRole("button", { name: copy.howItWorks.ctaPrimary }));
    await userEvent.click(screen.getByRole("radio", { name: copy.entryModes.uploadFile }));
    await userEvent.upload(
      screen.getByLabelText(copy.newTest.uploadFieldLabel),
      new File(["synthetic"], "contract.docx"),
    );
    const task = screen.getByLabelText(copy.newTest.taskLabel);
    await userEvent.type(task, "Resuma o contrato");
    await userEvent.click(screen.getByRole("button", { name: copy.newTest.continueToReview }));
    await screen.findByRole("heading", { name: copy.review.heading });

    await userEvent.click(screen.getByRole("button", { name: copy.review.backToCompose }));
    await userEvent.clear(screen.getByLabelText(copy.newTest.taskLabel));
    await userEvent.type(screen.getByLabelText(copy.newTest.taskLabel), "Liste os prazos");
    await userEvent.click(screen.getByRole("button", { name: copy.newTest.continueToReview }));
    await screen.findByRole("heading", { name: copy.review.heading });
    await userEvent.click(screen.getByRole("button", { name: copy.review.confirmSend }));

    await waitFor(() => expect(mockedExecuteDocument).toHaveBeenCalledTimes(1));
    expect(mockedPreviewDocument).toHaveBeenCalledTimes(2);
    expect(mockedExecuteDocument.mock.calls[0][0].get("confirmation_token")).toBe("second-token");
  });
});

async function goToReview() {
  render(<GuidedFlow />);

  await userEvent.click(screen.getByRole("button", { name: copy.howItWorks.ctaPrimary }));

  const select = await screen.findByLabelText(copy.newTest.exampleFieldLabel);
  await userEvent.selectOptions(select, "ex-1");
  await userEvent.click(screen.getByRole("button", { name: copy.newTest.continueToReview }));

  await screen.findByRole("heading", { name: copy.review.heading });
}

/** The one locale control in the header -- see `LocaleSwitcher.tsx`. */
function localeSwitcherButton() {
  return screen.getByRole("button", { name: /idioma|language/i });
}

async function switchToEnglish() {
  const button = localeSwitcherButton();
  if (button.textContent?.includes("English")) {
    return;
  }
  await userEvent.click(button);
}

async function goToResult() {
  mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: previewResponse() });
  mockedExecuteDisclosure.mockResolvedValue({ ok: true, data: executeResponse() });

  await goToReview();
  await userEvent.click(screen.getByRole("button", { name: copy.review.confirmSend }));
  await screen.findByRole("heading", { name: copy.result.heading });
}

describe("GuidedFlow -- execute is never called before the user confirms on review", () => {
  it("does not call executeDisclosure while walking welcome -> compose -> review", async () => {
    mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: previewResponse() });

    await goToReview();

    expect(mockedExecuteDisclosure).not.toHaveBeenCalled();
  });

  it("calls executeDisclosure exactly once after the user confirms", async () => {
    mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: previewResponse() });
    mockedExecuteDisclosure.mockResolvedValue({ ok: true, data: executeResponse() });

    await goToReview();
    expect(mockedExecuteDisclosure).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: copy.review.confirmSend }));

    await waitFor(() => expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1));
    await screen.findByRole("heading", { name: copy.result.heading });
  });
});

describe("GuidedFlow -- a blocked preview never reaches execute", () => {
  it("shows the blocked state and offers no way to call executeDisclosure", async () => {
    const blocked = previewResponse();
    blocked.summary.status = "blocked";
    mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: blocked });

    await goToReview();

    expect(screen.queryByRole("button", { name: copy.review.confirmSend })).not.toBeInTheDocument();
    expect(mockedExecuteDisclosure).not.toHaveBeenCalled();
  });
});

describe("GuidedFlow -- preview failure returns to compose without ever reaching execute", () => {
  it("shows the error and never calls executeDisclosure", async () => {
    mockedPreviewDisclosure.mockResolvedValue({
      ok: false,
      status: 500,
      error: { message: copy.errors.generic, kind: null, fields: null },
    });

    render(<GuidedFlow />);
    await userEvent.click(screen.getByRole("button", { name: copy.howItWorks.ctaPrimary }));
    const select = await screen.findByLabelText(copy.newTest.exampleFieldLabel);
    await userEvent.selectOptions(select, "ex-1");
    await userEvent.click(screen.getByRole("button", { name: copy.newTest.continueToReview }));

    await screen.findByText(copy.errors.generic);
    expect(mockedExecuteDisclosure).not.toHaveBeenCalled();
    expect(screen.queryByRole("heading", { name: copy.review.heading })).not.toBeInTheDocument();
  });
});

describe("GuidedFlow -- deterministic demo mode label reaches the result screen", () => {
  it("shows the label on the result screen when health says deterministic_demo_mode=true", async () => {
    mockedGetHealth.mockResolvedValue({ ok: true, data: healthResponse(true) });
    mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: previewResponse() });
    mockedExecuteDisclosure.mockResolvedValue({ ok: true, data: executeResponse() });

    await goToReview();
    await userEvent.click(screen.getByRole("button", { name: copy.review.confirmSend }));

    await screen.findByRole("heading", { name: copy.result.heading });
    expect(await screen.findByText(copy.provider.deterministicDemoLabel)).toBeInTheDocument();
  });
});

describe("GuidedFlow -- a failed /health still tells the user the mode is unknown", () => {
  it("shows the unverified-mode notice on the result screen when getHealth fails", async () => {
    // End-to-end version of the ResultScreen unit test: the failure has to
    // survive GuidedFlow's own health state, which is where the old
    // `if (result.ok)` swallowed it into an indistinguishable `null`.
    mockedGetHealth.mockResolvedValue({
      ok: false,
      status: 502,
      error: { message: copy.errors.generic, kind: null, fields: null },
    });
    mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: previewResponse() });
    mockedExecuteDisclosure.mockResolvedValue({ ok: true, data: executeResponse() });

    await goToReview();
    await userEvent.click(screen.getByRole("button", { name: copy.review.confirmSend }));

    await screen.findByRole("heading", { name: copy.result.heading });

    expect(await screen.findByText(copy.provider.modeUnverifiedLabel)).toBeInTheDocument();
    expect(screen.queryByText(copy.provider.deterministicDemoLabel)).not.toBeInTheDocument();
  });

  it("shows the unverified-mode notice when /health returns a body failing its contract", async () => {
    // Same user-visible outcome for a different upstream fault: with the
    // 200-body guard in place, a malformed /health is an ApiFailure, and it
    // must not silently degrade into "nothing to say about the provider".
    mockedGetHealth.mockResolvedValue({
      ok: false,
      status: 200,
      error: { message: copy.errors.generic, kind: null, fields: null },
    });
    mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: previewResponse() });
    mockedExecuteDisclosure.mockResolvedValue({ ok: true, data: executeResponse() });

    await goToReview();
    await userEvent.click(screen.getByRole("button", { name: copy.review.confirmSend }));

    await screen.findByRole("heading", { name: copy.result.heading });
    expect(await screen.findByText(copy.provider.modeUnverifiedLabel)).toBeInTheDocument();
  });
});

describe("GuidedFlow -- Comparar estratégias (T21 second slice)", () => {
  it("does not call compareStrategies until the user clicks Comparar estratégias", async () => {
    await goToResult();

    expect(mockedCompareStrategies).not.toHaveBeenCalled();
  });

  it("calls compareStrategies exactly once, with the same content/task/governance as the original test, only after the explicit click", async () => {
    mockedCompareStrategies.mockResolvedValue({ ok: true, data: compareResponse() });
    await goToResult();

    await userEvent.click(screen.getByRole("button", { name: copy.buttons.compareStrategies }));

    await waitFor(() => expect(mockedCompareStrategies).toHaveBeenCalledTimes(1));
    // Same request body the preview/execute calls used for this run --
    // built by the same `buildRequestBody(compose)`, never re-derived.
    expect(mockedCompareStrategies.mock.calls[0][0]).toEqual(mockedPreviewDisclosure.mock.calls[0][0]);
    expect(mockedCompareStrategies.mock.calls[0][0]).toEqual(mockedExecuteDisclosure.mock.calls[0][0]);
  });

  it("does not call executeDisclosure again when opening the comparison", async () => {
    mockedCompareStrategies.mockResolvedValue({ ok: true, data: compareResponse() });
    await goToResult();

    await userEvent.click(screen.getByRole("button", { name: copy.buttons.compareStrategies }));
    await screen.findByRole("heading", { name: copy.comparison.heading });

    expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1);
  });

  it("renders exactly five strategies, in canonical order, once the comparison loads", async () => {
    mockedCompareStrategies.mockResolvedValue({ ok: true, data: compareResponse() });
    await goToResult();

    await userEvent.click(screen.getByRole("button", { name: copy.buttons.compareStrategies }));
    await screen.findByRole("heading", { name: copy.comparison.heading });

    const order = ["b0", "b1", "b2", "b3", "b4"] as const;
    const names = order.map((code) => copy.treatments[code].name);
    const headings = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent ?? "");
    const positions = names.map((name) => headings.findIndex((h) => h.includes(name)));

    expect(positions.every((p) => p >= 0)).toBe(true);
    expect(positions).toEqual([...positions].sort((a, b) => a - b));
  });

  it("shows the explicit B0 warning once the comparison loads", async () => {
    mockedCompareStrategies.mockResolvedValue({ ok: true, data: compareResponse() });
    await goToResult();

    await userEvent.click(screen.getByRole("button", { name: copy.buttons.compareStrategies }));

    expect(await screen.findByText(copy.comparison.unsafeControlHeading)).toBeInTheDocument();
  });

  it("shows a safe generic error and returns to Result when the comparison request fails", async () => {
    mockedCompareStrategies.mockResolvedValue({
      ok: false,
      status: 500,
      error: { message: copy.errors.generic, kind: null, fields: null },
    });
    await goToResult();

    await userEvent.click(screen.getByRole("button", { name: copy.buttons.compareStrategies }));

    await screen.findByRole("heading", { name: copy.result.heading });
    expect(screen.getByText(copy.errors.generic)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: copy.comparison.heading })).not.toBeInTheDocument();
  });

  it("returning from the comparison preserves the original Result screen", async () => {
    mockedCompareStrategies.mockResolvedValue({ ok: true, data: compareResponse() });
    await goToResult();

    const finalAnswer = executeResponse().final_answer as string;
    expect(screen.getByText(finalAnswer)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: copy.buttons.compareStrategies }));
    await screen.findByRole("heading", { name: copy.comparison.heading });

    await userEvent.click(screen.getByRole("button", { name: copy.comparison.backToResult }));

    await screen.findByRole("heading", { name: copy.result.heading });
    expect(screen.getByText(finalAnswer)).toBeInTheDocument();
    // The original result was not re-fetched to get back here.
    expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1);
  });

  it("shows a named loading state while the comparison is in flight, never a generic spinner", async () => {
    let resolveCompare!: (value: Awaited<ReturnType<typeof compareStrategies>>) => void;
    mockedCompareStrategies.mockReturnValue(
      new Promise((resolve) => {
        resolveCompare = resolve;
      }),
    );
    await goToResult();

    await userEvent.click(screen.getByRole("button", { name: copy.buttons.compareStrategies }));

    expect(await screen.findByText(copy.processingStages.comparingStrategies)).toBeInTheDocument();

    resolveCompare({ ok: true, data: compareResponse() });
    await screen.findByRole("heading", { name: copy.comparison.heading });
  });
});

describe("GuidedFlow -- Ver detalhes técnicos (T21 third slice)", () => {
  it("shows the Ver detalhes técnicos action on Resultado", async () => {
    await goToResult();

    expect(screen.getByRole("button", { name: copy.buttons.viewTechnicalDetails })).toBeInTheDocument();
  });

  it("opens the technical details screen on click, without calling preview/execute/compare again", async () => {
    await goToResult();

    await userEvent.click(screen.getByRole("button", { name: copy.buttons.viewTechnicalDetails }));

    await screen.findByRole("heading", { name: copy.sectionHeadings.technicalDetails });
    expect(mockedPreviewDisclosure).toHaveBeenCalledTimes(1);
    expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1);
    expect(mockedCompareStrategies).not.toHaveBeenCalled();
  });

  it("reuses the same ExecuteResponse already held by Resultado -- strategy and treatment render correctly", async () => {
    await goToResult();

    await userEvent.click(screen.getByRole("button", { name: copy.buttons.viewTechnicalDetails }));
    await screen.findByRole("heading", { name: copy.sectionHeadings.technicalDetails });

    const e = executeResponse();
    expect(screen.getByText(e.strategy)).toBeInTheDocument();
    expect(screen.getByText(e.treatment)).toBeInTheDocument();
  });

  it("returning restores the original Resultado without re-running preview, execute or compare", async () => {
    await goToResult();

    const finalAnswer = executeResponse().final_answer as string;
    expect(screen.getByText(finalAnswer)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: copy.buttons.viewTechnicalDetails }));
    await screen.findByRole("heading", { name: copy.sectionHeadings.technicalDetails });

    await userEvent.click(screen.getByRole("button", { name: copy.technicalDetails.backToResult }));

    await screen.findByRole("heading", { name: copy.result.heading });
    expect(screen.getByText(finalAnswer)).toBeInTheDocument();
    expect(mockedPreviewDisclosure).toHaveBeenCalledTimes(1);
    expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1);
    expect(mockedCompareStrategies).not.toHaveBeenCalled();
  });

  /**
   * Adversarial leak test (CLAUDE.md's no-leak invariant): plants a marker
   * in `PreviewResponse.external_payload` -- a field that IS on the same
   * flow state the technical-details screen is wired from, but that screen
   * must never read (its own explicit-reveal surface is Revisão/Comparação,
   * not this screen). This is the realistic failure mode a careless
   * implementation could hit: passing `preview` into `TechnicalDetailsScreen`
   * or otherwise threading `external_payload` through.
   */
  it("never renders external_payload on the technical details screen", async () => {
    const preview = previewResponse();
    preview.external_payload = "SESSION_SECRET_MARKER";
    mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: preview });
    mockedExecuteDisclosure.mockResolvedValue({ ok: true, data: executeResponse() });

    await goToReview();
    await userEvent.click(screen.getByRole("button", { name: copy.review.confirmSend }));
    await screen.findByRole("heading", { name: copy.result.heading });

    await userEvent.click(screen.getByRole("button", { name: copy.buttons.viewTechnicalDetails }));
    await screen.findByRole("heading", { name: copy.sectionHeadings.technicalDetails });

    expect(screen.queryByText(/SESSION_SECRET_MARKER/)).not.toBeInTheDocument();
  });
});

/**
 * T21 fourth slice / #29: pt-BR / English localization. The locale
 * control lives in the header (`GuidedFlow`'s `styles.header`, next to
 * `ThemeToggle`) and stays mounted across every screen, so these tests
 * exercise it from wherever the flow currently is.
 */
describe("GuidedFlow -- locale switcher (T21 fourth slice)", () => {
  it("first visit uses pt-BR and the switcher shows the current locale", () => {
    render(<GuidedFlow />);
    expect(screen.getByRole("heading", { name: copy.howItWorks.title })).toBeInTheDocument();
    expect(localeSwitcherButton().textContent).toMatch(/português/i);
  });

  it("switching to English updates the UI without a reload", async () => {
    render(<GuidedFlow />);
    await switchToEnglish();

    expect(screen.getByRole("heading", { name: en.howItWorks.title })).toBeInTheDocument();
    expect(localeSwitcherButton().textContent).toMatch(/english/i);
    expect(screen.queryByText(copy.howItWorks.title)).not.toBeInTheDocument();
  });

  it("switching back to Portuguese works", async () => {
    render(<GuidedFlow />);
    await switchToEnglish();
    await userEvent.click(localeSwitcherButton());

    expect(screen.getByRole("heading", { name: copy.howItWorks.title })).toBeInTheDocument();
    expect(localeSwitcherButton().textContent).toMatch(/português/i);
  });

  it("persists the choice to localStorage", async () => {
    render(<GuidedFlow />);
    await switchToEnglish();

    expect(readStoredLocale()).toBe("en");
  });

  it("a remount restores the stored locale", async () => {
    const { unmount } = render(<GuidedFlow />);
    await switchToEnglish();
    unmount();

    render(<GuidedFlow />);
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: en.howItWorks.title })).toBeInTheDocument(),
    );
  });

  it("an invalid stored locale falls back to pt-BR", async () => {
    window.localStorage.setItem("adg-locale", "klingon");
    render(<GuidedFlow />);

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: copy.howItWorks.title })).toBeInTheDocument(),
    );
  });
});

describe("GuidedFlow -- switching locale never re-fetches preview/execute/compare (T21 fourth slice)", () => {
  it("does not re-call previewDisclosure/executeDisclosure when switching locale on Resultado", async () => {
    mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: previewResponse() });
    mockedExecuteDisclosure.mockResolvedValue({ ok: true, data: executeResponse() });
    await goToResult();

    await switchToEnglish();

    expect(mockedPreviewDisclosure).toHaveBeenCalledTimes(1);
    expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1);
    expect(mockedCompareStrategies).not.toHaveBeenCalled();
    // The result data itself is unchanged by the locale switch -- only its
    // presentation is.
    expect(screen.getByText(executeResponse().final_answer as string)).toBeInTheDocument();
  });

  it("does not re-call compareStrategies when switching locale on the comparison screen, and keeps the same entries", async () => {
    mockedCompareStrategies.mockResolvedValue({ ok: true, data: compareResponse() });
    await goToResult();
    await userEvent.click(screen.getByRole("button", { name: copy.buttons.compareStrategies }));
    await screen.findByRole("heading", { name: copy.comparison.heading });

    await switchToEnglish();

    expect(mockedCompareStrategies).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("heading", { name: en.comparison.heading })).toBeInTheDocument();
    expect(screen.getByText(en.treatments.b0.name)).toBeInTheDocument();
    expect(screen.getByText(en.treatments.b4.name)).toBeInTheDocument();
    expect(screen.getByText(en.comparison.unsafeControlHeading)).toBeInTheDocument();
  });

  it("does not re-call anything when switching locale on the technical details screen, and keeps the same ExecuteResponse", async () => {
    await goToResult();
    await userEvent.click(screen.getByRole("button", { name: copy.buttons.viewTechnicalDetails }));
    await screen.findByRole("heading", { name: copy.sectionHeadings.technicalDetails });

    await switchToEnglish();

    expect(mockedPreviewDisclosure).toHaveBeenCalledTimes(1);
    expect(mockedExecuteDisclosure).toHaveBeenCalledTimes(1);
    expect(mockedCompareStrategies).not.toHaveBeenCalled();
    const e = executeResponse();
    expect(screen.getByText(e.strategy)).toBeInTheDocument();
    expect(screen.getByText(e.treatment)).toBeInTheDocument();
    expect(screen.getByText(en.technicalDetails.executionHeading)).toBeInTheDocument();
  });
});

describe("GuidedFlow -- error messages switch with the locale", () => {
  it("shows the English generic error message when a preview fails after switching to English", async () => {
    mockedPreviewDisclosure.mockResolvedValue({
      ok: false,
      status: 500,
      error: { message: en.errors.generic, kind: null, fields: null },
    });

    render(<GuidedFlow />);
    await switchToEnglish();
    await userEvent.click(screen.getByRole("button", { name: en.howItWorks.ctaPrimary }));
    const select = await screen.findByLabelText(en.newTest.exampleFieldLabel);
    await userEvent.selectOptions(select, "ex-1");
    await userEvent.click(screen.getByRole("button", { name: en.newTest.continueToReview }));

    await screen.findByText(en.errors.generic);
    expect(screen.queryByText(copy.errors.generic)).not.toBeInTheDocument();
  });
});

describe("GuidedFlow -- no sensitive information reaches the DOM because of the locale switch", () => {
  it("switching locale on the review screen never renders external_payload before its own disclosure is opened", async () => {
    const preview = previewResponse();
    preview.external_payload = "LOCALE_SWITCH_MARKER";
    mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: preview });

    await goToReview();
    await switchToEnglish();

    expect(screen.queryByText(/LOCALE_SWITCH_MARKER/)).not.toBeInTheDocument();
  });

  it("switching locale on the technical details screen still never renders external_payload", async () => {
    const preview = previewResponse();
    preview.external_payload = "SESSION_SECRET_MARKER";
    mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: preview });
    mockedExecuteDisclosure.mockResolvedValue({ ok: true, data: executeResponse() });

    await goToReview();
    await userEvent.click(screen.getByRole("button", { name: copy.review.confirmSend }));
    await screen.findByRole("heading", { name: copy.result.heading });
    await userEvent.click(screen.getByRole("button", { name: copy.buttons.viewTechnicalDetails }));
    await screen.findByRole("heading", { name: copy.sectionHeadings.technicalDetails });

    await switchToEnglish();

    expect(screen.queryByText(/SESSION_SECRET_MARKER/)).not.toBeInTheDocument();
  });
});

/**
 * T28 / issue #70: `getDemoFeatures` is fetched once, up front, and its
 * result (or absence of a successful one) gates whether the export/restore
 * panel renders on Revisão at all. Every OTHER test in this file relies on
 * the `beforeEach` default (`{ demo_transparency_enabled: false, demo_vault_explorer_enabled: false }`) and is
 * therefore itself a "disabled" regression test; these are the explicit
 * ones plus the "request fails" and "enabled" cases.
 */
describe("GuidedFlow -- demo transparency feature flag (T28)", () => {
  it("renders no export/restore panel on Revisão when the flag is disabled (default)", async () => {
    mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: previewResponse() });

    await goToReview();

    expect(screen.queryByText(copy.exportRestorePanel.heading)).not.toBeInTheDocument();
  });

  it("renders no export/restore panel when the features request itself fails", async () => {
    mockedGetDemoFeatures.mockResolvedValue({
      ok: false,
      status: 500,
      error: { message: copy.errors.generic, kind: null, fields: null },
    });
    mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: previewResponse() });

    await goToReview();

    expect(screen.queryByText(copy.exportRestorePanel.heading)).not.toBeInTheDocument();
  });

  it("renders the export/restore panel on Revisão when the flag is enabled and the preview is allowed", async () => {
    mockedGetDemoFeatures.mockResolvedValue({ ok: true, data: { demo_transparency_enabled: true, demo_vault_explorer_enabled: false } });
    mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: previewResponse() });

    await goToReview();

    await userEvent.click(await screen.findByText(copy.review.technicalToolsToggle));
    expect(await screen.findByText(copy.exportRestorePanel.heading)).toBeInTheDocument();
  });

  it("does not call getDemoFeatures more than once across a full run", async () => {
    mockedGetDemoFeatures.mockResolvedValue({ ok: true, data: { demo_transparency_enabled: true, demo_vault_explorer_enabled: false } });
    mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: previewResponse() });
    mockedExecuteDisclosure.mockResolvedValue({ ok: true, data: executeResponse() });

    await goToReview();
    await userEvent.click(await screen.findByText(copy.review.technicalToolsToggle));
    await screen.findByText(copy.exportRestorePanel.heading);
    await userEvent.click(screen.getByRole("button", { name: copy.review.confirmSend }));
    await screen.findByRole("heading", { name: copy.result.heading });

    expect(mockedGetDemoFeatures).toHaveBeenCalledTimes(1);
  });
});

/**
 * T29 / issue #72: `demo_vault_explorer_enabled` is read from the SAME
 * single `getDemoFeatures` fetch above, never a second request, and gates
 * `VaultExplorerPanel` on both Revisão and Resultado. Every OTHER test in
 * this file relies on the `beforeEach` default (`demo_vault_explorer_enabled:
 * false`) and is therefore itself a "disabled" regression test; these are
 * the explicit "request fails" and "enabled" cases, on both screens.
 */
describe("GuidedFlow -- demo vault explorer feature flag (T29)", () => {
  it("renders no Vault Explorer panel on Revisão when the flag is disabled (default), even with a non-null token", async () => {
    mockedPreviewDisclosure.mockResolvedValue({
      ok: true,
      data: { ...previewResponse(), vault_explorer_token: "vx1.token" },
    });

    await goToReview();

    expect(screen.queryByText(copy.vaultExplorerPanel.heading)).not.toBeInTheDocument();
  });

  it("renders no Vault Explorer panel when the features request itself fails", async () => {
    mockedGetDemoFeatures.mockResolvedValue({
      ok: false,
      status: 500,
      error: { message: copy.errors.generic, kind: null, fields: null },
    });
    mockedPreviewDisclosure.mockResolvedValue({
      ok: true,
      data: { ...previewResponse(), vault_explorer_token: "vx1.token" },
    });

    await goToReview();

    expect(screen.queryByText(copy.vaultExplorerPanel.heading)).not.toBeInTheDocument();
  });

  it("renders the Vault Explorer panel on Revisão and Resultado when the flag is enabled, sharing the same token", async () => {
    mockedGetDemoFeatures.mockResolvedValue({
      ok: true,
      data: { demo_transparency_enabled: false, demo_vault_explorer_enabled: true },
    });
    mockedPreviewDisclosure.mockResolvedValue({
      ok: true,
      data: { ...previewResponse(), vault_explorer_token: "vx1.shared-token" },
    });
    mockedExecuteDisclosure.mockResolvedValue({ ok: true, data: executeResponse() });

    await goToReview();
    await userEvent.click(await screen.findByText(copy.review.technicalToolsToggle));
    expect(await screen.findByText(copy.vaultExplorerPanel.heading)).toBeInTheDocument();
    expect(screen.getByText(copy.vaultExplorerPanel.toggleLabel)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: copy.review.confirmSend }));
    await screen.findByRole("heading", { name: copy.result.heading });

    expect(screen.getByText(copy.vaultExplorerPanel.heading)).toBeInTheDocument();
    expect(screen.getByText(copy.vaultExplorerPanel.toggleLabel)).toBeInTheDocument();
  });

  it("renders the panel's unavailable note on Resultado when the flag is enabled but the token is null", async () => {
    mockedGetDemoFeatures.mockResolvedValue({
      ok: true,
      data: { demo_transparency_enabled: false, demo_vault_explorer_enabled: true },
    });
    mockedPreviewDisclosure.mockResolvedValue({ ok: true, data: previewResponse() });
    mockedExecuteDisclosure.mockResolvedValue({ ok: true, data: executeResponse() });

    await goToReview();
    await userEvent.click(screen.getByRole("button", { name: copy.review.confirmSend }));
    await screen.findByRole("heading", { name: copy.result.heading });

    expect(screen.getByText(copy.vaultExplorerPanel.unavailableForDecision)).toBeInTheDocument();
  });
});
