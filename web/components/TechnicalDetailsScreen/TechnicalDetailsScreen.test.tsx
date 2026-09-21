import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithLocale } from "@/i18n/renderWithLocale";
import type { ExecuteResponse } from "@/lib/contracts";
import { copy } from "@/lib/copy";
import { en } from "@/lib/copy.en";

import { TechnicalDetailsScreen } from "./TechnicalDetailsScreen";

beforeEach(() => {
  window.localStorage.clear();
});

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
    final_answer: "Esta é a resposta final reconstruída.",
    provider: {
      called: true,
      provider_class: "FakeProvider",
      model_id: "fake-1",
      model_snapshot: "2026-01-01",
      decoding_config: { temperature: 0.2, max_tokens: 256 },
      transmitted_bytes: 128,
      response_hash: "RESPONSE_HASH_ABC",
      failed: false,
      failure_kind: null,
    },
    reconstruction: {
      attempted: true,
      reconstructed_hash: "RECONSTRUCTED_HASH_DEF",
      changed_from_provider_response: false,
    },
    treatment: "b4",
    strategy: "recommended",
    governance: {
      domain: "hr",
      purpose: "team_summary",
      policy_version: "hr-v1",
      provider_class: "FakeProvider",
      requester_role: "manager",
      requested_pseudonym_scope: "session",
    },
    total_ms: 123.4,
    ...overrides,
  };
}

/**
 * T30 / issue #82: this screen frames itself explicitly as the technical/
 * audit level, ahead of its own heading, so a visitor who lands here (e.g.
 * from Result's "Detalhes técnicos e ferramentas de pesquisa") never
 * mistakes it for part of the primary task flow.
 */
describe("TechnicalDetailsScreen -- technical/audit surface framing (T30)", () => {
  it("renders a technical-level eyebrow label before the heading", () => {
    render(<TechnicalDetailsScreen execute={execute()} onBack={vi.fn()} />);

    const surfaceLabel = screen.getByText(copy.technicalDetails.surfaceLabel);
    const heading = screen.getByRole("heading", { name: copy.sectionHeadings.technicalDetails });
    expect(surfaceLabel.compareDocumentPosition(heading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});

describe("TechnicalDetailsScreen -- Execução: strategy vs treatment", () => {
  it("renders both the requested strategy and the executed treatment as raw codes", () => {
    render(<TechnicalDetailsScreen execute={execute()} onBack={vi.fn()} />);

    expect(screen.getByText("recommended")).toBeInTheDocument();
    expect(screen.getByText("b4")).toBeInTheDocument();
  });

  it("explains the strategy-vs-treatment distinction in plain language", () => {
    render(<TechnicalDetailsScreen execute={execute()} onBack={vi.fn()} />);

    expect(screen.getByText(copy.technicalDetails.strategyVsTreatmentExplanation)).toBeInTheDocument();
  });
});

describe("TechnicalDetailsScreen -- Governança", () => {
  it("renders every SafeGovernanceView field", () => {
    render(<TechnicalDetailsScreen execute={execute()} onBack={vi.fn()} />);

    expect(screen.getByText("hr")).toBeInTheDocument();
    expect(screen.getByText("team_summary")).toBeInTheDocument();
    expect(screen.getByText("hr-v1")).toBeInTheDocument();
    expect(screen.getByText("manager")).toBeInTheDocument();
    expect(screen.getByText("session")).toBeInTheDocument();
    expect(screen.getAllByText("FakeProvider").length).toBeGreaterThan(0);
  });

  it("renders a readable fallback for a null optional governance field, never an error", () => {
    render(
      <TechnicalDetailsScreen
        execute={execute({
          governance: {
            domain: "hr",
            purpose: "team_summary",
            policy_version: "hr-v1",
            provider_class: "FakeProvider",
            requester_role: null,
            requested_pseudonym_scope: "session",
          },
        })}
        onBack={vi.fn()}
      />,
    );

    expect(screen.getByText(copy.technicalDetails.notInformed)).toBeInTheDocument();
  });
});

describe("TechnicalDetailsScreen -- Provedor", () => {
  it("renders the safe provider fields, including bounded decoding_config rows", () => {
    render(<TechnicalDetailsScreen execute={execute()} onBack={vi.fn()} />);

    expect(screen.getByText("fake-1")).toBeInTheDocument();
    expect(screen.getByText("2026-01-01")).toBeInTheDocument();
    expect(screen.getByText("128")).toBeInTheDocument();
    expect(screen.getByText("temperature")).toBeInTheDocument();
    expect(screen.getByText("0.2")).toBeInTheDocument();
    expect(screen.getByText("max_tokens")).toBeInTheDocument();
    expect(screen.getByText("256")).toBeInTheDocument();
  });

  it("keeps response_hash out of the tree until its own disclosure is opened", async () => {
    render(<TechnicalDetailsScreen execute={execute()} onBack={vi.fn()} />);

    expect(screen.queryByText("RESPONSE_HASH_ABC")).not.toBeInTheDocument();

    await userEvent.click(screen.getByText(copy.technicalDetails.providerHashToggle));

    expect(screen.getByText("RESPONSE_HASH_ABC")).toBeInTheDocument();
  });

  it("handles the provider-not-called state without showing any other provider field", () => {
    render(
      <TechnicalDetailsScreen
        execute={execute({
          provider: {
            called: false,
            provider_class: null,
            model_id: null,
            model_snapshot: null,
            decoding_config: null,
            transmitted_bytes: null,
            response_hash: null,
            failed: false,
            failure_kind: null,
          },
        })}
        onBack={vi.fn()}
      />,
    );

    expect(screen.getByText(copy.technicalDetails.providerNotCalledText)).toBeInTheDocument();
    expect(screen.queryByText(copy.technicalDetails.providerDecodingConfigHeading)).not.toBeInTheDocument();
  });

  it("renders only the safe failure_kind category for a failed provider call, nothing else", () => {
    render(
      <TechnicalDetailsScreen
        execute={execute({
          provider: {
            called: true,
            provider_class: "FakeProvider",
            model_id: "fake-1",
            model_snapshot: "2026-01-01",
            decoding_config: null,
            transmitted_bytes: null,
            response_hash: null,
            failed: true,
            failure_kind: "ProviderTimeoutError",
          },
        })}
        onBack={vi.fn()}
      />,
    );

    expect(screen.getByText("ProviderTimeoutError")).toBeInTheDocument();
    expect(screen.getByText(copy.technicalDetails.providerFailedExplanation)).toBeInTheDocument();
    // The failed branch never renders model_id/model_snapshot/decoding_config
    // rows -- only the safe failure category, per CLAUDE.md's no-leak rule
    // for anything provider/exception-shaped.
    expect(screen.queryByText(copy.technicalDetails.providerDecodingConfigHeading)).not.toBeInTheDocument();
    expect(screen.queryByText(copy.technicalDetails.providerModelIdLabel)).not.toBeInTheDocument();
  });
});

describe("TechnicalDetailsScreen -- Reconstrução local", () => {
  it("renders attempted/changed metadata and explains what local reconstruction means", () => {
    render(<TechnicalDetailsScreen execute={execute()} onBack={vi.fn()} />);

    expect(screen.getByText(copy.technicalDetails.reconstructionExplanation)).toBeInTheDocument();
    expect(screen.getAllByText(copy.technicalDetails.yes).length).toBeGreaterThan(0);
    expect(screen.getAllByText(copy.technicalDetails.no).length).toBeGreaterThan(0);
  });

  it("keeps reconstructed_hash out of the tree until its own disclosure is opened", async () => {
    render(<TechnicalDetailsScreen execute={execute()} onBack={vi.fn()} />);

    expect(screen.queryByText("RECONSTRUCTED_HASH_DEF")).not.toBeInTheDocument();

    await userEvent.click(screen.getByText(copy.technicalDetails.reconstructionHashToggle));

    expect(screen.getByText("RECONSTRUCTED_HASH_DEF")).toBeInTheDocument();
  });

  it("does not offer the hash disclosure at all when reconstruction was never attempted", () => {
    render(
      <TechnicalDetailsScreen
        execute={execute({
          reconstruction: { attempted: false, reconstructed_hash: null, changed_from_provider_response: null },
        })}
        onBack={vi.fn()}
      />,
    );

    expect(screen.queryByText(copy.technicalDetails.reconstructionHashToggle)).not.toBeInTheDocument();
  });
});

describe("TechnicalDetailsScreen -- Tempo operacional", () => {
  it("shows total_ms", () => {
    render(<TechnicalDetailsScreen execute={execute({ total_ms: 987.6 })} onBack={vi.fn()} />);

    expect(screen.getByText(/987\.6/)).toBeInTheDocument();
  });

  it("states explicitly that this is not the scientific latency metric used in the experiments", () => {
    render(<TechnicalDetailsScreen execute={execute()} onBack={vi.fn()} />);

    expect(screen.getByText(copy.technicalDetails.timingExplanation)).toBeInTheDocument();
    expect(screen.getByText(/não é a métrica científica/i)).toBeInTheDocument();
  });
});

describe("TechnicalDetailsScreen -- navigation back to Result", () => {
  it("calls onBack when the back action is used", async () => {
    const onBack = vi.fn();
    render(<TechnicalDetailsScreen execute={execute()} onBack={onBack} />);

    await userEvent.click(screen.getByRole("button", { name: copy.technicalDetails.backToResult }));

    expect(onBack).toHaveBeenCalledTimes(1);
  });
});

describe("TechnicalDetailsScreen -- never a scientific/ranking surface", () => {
  it("never renders exposure/utility score, winner or ranking language", () => {
    render(<TechnicalDetailsScreen execute={execute()} onBack={vi.fn()} />);

    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(
      /exposure score|utility score|winner|best strategy|pontuação de exposição|pontuação de utilidade|vencedor|melhor estratégia|ranking/i,
    );
  });
});

/**
 * Adversarial leak tests (CLAUDE.md's no-leak invariant): this component
 * reads only `execute: ExecuteResponse` and deliberately never reads
 * `final_answer` or `summary.categories` -- both present on the SAME
 * `ExecuteResponse` prop but outside this screen's presentation allowlist
 * (`strategy`/`treatment`/`governance`/`provider`/`reconstruction`/
 * `total_ms`). Markers are planted in exactly those two fields to prove a
 * careless "just render everything from execute" implementation would be
 * caught.
 */
describe("TechnicalDetailsScreen -- adversarial: fields outside the allowlist never reach the DOM", () => {
  it("never renders final_answer, even though it is on the same ExecuteResponse", () => {
    render(
      <TechnicalDetailsScreen
        execute={execute({ final_answer: "CPF_SECRET_MARKER" })}
        onBack={vi.fn()}
      />,
    );

    expect(screen.queryByText(/CPF_SECRET_MARKER/)).not.toBeInTheDocument();
  });

  it("never renders category technical_reason text, even though summary is on the same ExecuteResponse", () => {
    render(
      <TechnicalDetailsScreen
        execute={execute({
          summary: {
            status: "allowed",
            categories: [
              {
                category: "employee_name",
                outcome: "pseudonymized",
                action: "pseudonymize",
                crosses_trust_boundary: true,
                occurrence_count: 1,
                required_for_task: null,
                technical_reason: "PROVIDER_SECRET_MARKER",
                policy_version: "hr-v1",
                policy_restricted: null,
                impossible_under_policy: null,
              },
            ],
            detected_span_count: 1,
            detected_categories: ["employee_name"],
          },
        })}
        onBack={vi.fn()}
      />,
    );

    expect(screen.queryByText(/PROVIDER_SECRET_MARKER/)).not.toBeInTheDocument();
  });
});

describe("TechnicalDetailsScreen -- switches to English (T21 fourth slice)", () => {
  it("renders English section headings/explanations while keeping strategy/treatment codes identical", async () => {
    await renderWithLocale(<TechnicalDetailsScreen execute={execute()} onBack={vi.fn()} />, "en");

    // Technical identifiers stay byte-identical regardless of locale.
    expect(screen.getByText("recommended")).toBeInTheDocument();
    expect(screen.getByText("b4")).toBeInTheDocument();

    expect(screen.getByText(en.technicalDetails.executionHeading)).toBeInTheDocument();
    expect(screen.getByText(en.technicalDetails.strategyVsTreatmentExplanation)).toBeInTheDocument();
    expect(screen.getByText(en.technicalDetails.governanceHeading)).toBeInTheDocument();
    expect(screen.getByText(en.technicalDetails.timingExplanation)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: en.technicalDetails.backToResult })).toBeInTheDocument();
    expect(screen.queryByText(copy.technicalDetails.executionHeading)).not.toBeInTheDocument();
  });

  it("keeps hashes behind the English toggle text, revealed only on click", async () => {
    await renderWithLocale(<TechnicalDetailsScreen execute={execute()} onBack={vi.fn()} />, "en");

    expect(screen.queryByText("RESPONSE_HASH_ABC")).not.toBeInTheDocument();

    await userEvent.click(screen.getByText(en.technicalDetails.providerHashToggle));

    expect(screen.getByText("RESPONSE_HASH_ABC")).toBeInTheDocument();
  });
});
