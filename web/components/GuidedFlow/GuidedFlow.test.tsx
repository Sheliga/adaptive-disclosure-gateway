import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { executeDisclosure, getExamples, getHealth, previewDisclosure } from "@/lib/api";
import type { ExecuteResponse, HealthResponse, PreviewResponse } from "@/lib/contracts";
import { copy } from "@/lib/copy";

import { GuidedFlow } from "./GuidedFlow";

vi.mock("@/lib/api", () => ({
  getHealth: vi.fn(),
  getExamples: vi.fn(),
  previewDisclosure: vi.fn(),
  executeDisclosure: vi.fn(),
}));

const mockedGetHealth = vi.mocked(getHealth);
const mockedGetExamples = vi.mocked(getExamples);
const mockedPreviewDisclosure = vi.mocked(previewDisclosure);
const mockedExecuteDisclosure = vi.mocked(executeDisclosure);

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
    treatment: "policy_governed",
    strategy: "recommended",
    governance: {
      domain: "demo",
      purpose: "demo",
      policy_version: "v1",
      provider_class: "FakeProvider",
      requester_role: null,
      requested_pseudonym_scope: "none",
    },
    provider_mode: { provider_class: "FakeProvider" },
  };
}

function executeResponse(): ExecuteResponse {
  return {
    contract_version: "t20-application-api-v1",
    status: "completed",
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
    treatment: "policy_governed",
    strategy: "recommended",
    governance: {
      domain: "demo",
      purpose: "demo",
      policy_version: "v1",
      provider_class: "FakeProvider",
      requester_role: null,
      requested_pseudonym_scope: "none",
    },
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
  window.localStorage.clear();
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
});

async function goToReview() {
  render(<GuidedFlow />);

  await userEvent.click(screen.getByRole("button", { name: copy.howItWorks.ctaPrimary }));

  const select = await screen.findByLabelText(copy.newTest.exampleFieldLabel);
  await userEvent.selectOptions(select, "ex-1");
  await userEvent.click(screen.getByRole("button", { name: copy.newTest.continueToReview }));

  await screen.findByRole("heading", { name: copy.review.heading });
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
