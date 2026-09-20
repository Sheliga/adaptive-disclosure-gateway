import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithLocale } from "@/i18n/renderWithLocale";
import type { ExecuteResponse, HealthResponse } from "@/lib/contracts";
import type { ProviderModeState } from "@/lib/providerMode";
import { copy } from "@/lib/copy";
import { en } from "@/lib/copy.en";

import { ResultScreen } from "./ResultScreen";

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

function healthState(deterministicDemoMode: boolean): ProviderModeState {
  return { status: "ready", health: healthBody(deterministicDemoMode) };
}

function healthBody(deterministicDemoMode: boolean): HealthResponse {
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

describe("ResultScreen -- final answer is the primary output", () => {
  it("renders the final answer and the trust-boundary path on success", () => {
    const e = execute();
    render(<ResultScreen execute={e} health={{ status: "loading" }} onRestart={vi.fn()} compareError={null} onCompareStrategies={vi.fn()} onViewTechnicalDetails={vi.fn()} />);

    expect(screen.getByText(e.final_answer as string)).toBeInTheDocument();
    expect(screen.getAllByText(copy.result.pathLocal).length).toBe(2);
    expect(screen.getByText(copy.result.pathProvider)).toBeInTheDocument();
  });
});

describe("ResultScreen -- blocked execution", () => {
  it("renders the blocked state, not a crash or a fabricated answer", () => {
    const e = execute({ summary: { status: "blocked", categories: [], detected_span_count: 0, detected_categories: [] } });
    render(<ResultScreen execute={e} health={{ status: "loading" }} onRestart={vi.fn()} compareError={null} onCompareStrategies={vi.fn()} onViewTechnicalDetails={vi.fn()} />);

    expect(screen.getByText(copy.result.blockedHeading)).toBeInTheDocument();
    expect(screen.queryByText(e.final_answer as string)).not.toBeInTheDocument();
  });
});

describe("ResultScreen -- failed provider call", () => {
  it("renders a recorded provider failure, never a fabricated answer", () => {
    const e = execute({
      final_answer: null,
      provider: {
        called: true,
        provider_class: "FakeProvider",
        model_id: "fake-1",
        model_snapshot: "2026-01-01",
        decoding_config: null,
        transmitted_bytes: null,
        response_hash: null,
        failed: true,
        failure_kind: "timeout",
      },
    });
    render(<ResultScreen execute={e} health={{ status: "loading" }} onRestart={vi.fn()} compareError={null} onCompareStrategies={vi.fn()} onViewTechnicalDetails={vi.fn()} />);

    expect(screen.getByText(copy.result.providerFailedHeading)).toBeInTheDocument();
    expect(screen.getByText("timeout")).toBeInTheDocument();
    expect(screen.queryByText(copy.sectionHeadings.finalAnswer)).not.toBeInTheDocument();
  });
});

describe("ResultScreen -- deterministic demo mode label", () => {
  it("appears when health.provider.deterministic_demo_mode is true", () => {
    render(<ResultScreen execute={execute()} health={healthState(true)} onRestart={vi.fn()} compareError={null} onCompareStrategies={vi.fn()} onViewTechnicalDetails={vi.fn()} />);
    expect(screen.getByText(copy.provider.deterministicDemoLabel)).toBeInTheDocument();
  });

  it("does not appear when it is false", () => {
    render(<ResultScreen execute={execute()} health={healthState(false)} onRestart={vi.fn()} compareError={null} onCompareStrategies={vi.fn()} onViewTechnicalDetails={vi.fn()} />);
    expect(screen.queryByText(copy.provider.deterministicDemoLabel)).not.toBeInTheDocument();
  });

  it("does not appear while the health check is still in flight", () => {
    render(<ResultScreen execute={execute()} health={{ status: "loading" }} onRestart={vi.fn()} compareError={null} onCompareStrategies={vi.fn()} onViewTechnicalDetails={vi.fn()} />);
    expect(screen.queryByText(copy.provider.deterministicDemoLabel)).not.toBeInTheDocument();
  });
});

describe("ResultScreen -- restart", () => {
  it("calls onRestart when the restart button is clicked", async () => {
    const onRestart = vi.fn();
    render(
      <ResultScreen
        execute={execute()}
        health={{ status: "loading" }}
        onRestart={onRestart}
        compareError={null}
        onCompareStrategies={vi.fn()}
        onViewTechnicalDetails={vi.fn()}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: copy.result.restart }));
    expect(onRestart).toHaveBeenCalledTimes(1);
  });
});

describe("ResultScreen -- the protections summary speaks human, not identifiers", () => {
  function withCategories(): ExecuteResponse {
    return execute({
      summary: {
        status: "allowed",
        categories: [
          {
            category: "employee_name",
            outcome: "pseudonymized",
            action: "pseudonymize",
            crosses_trust_boundary: true,
            occurrence_count: 2,
            required_for_task: null,
            technical_reason: "policy hr-v1 rule",
            policy_version: "hr-v1",
            policy_restricted: null,
            impossible_under_policy: null,
          },
          {
            category: "cpf",
            outcome: "removed",
            action: "remove",
            crosses_trust_boundary: false,
            occurrence_count: 1,
            required_for_task: null,
            technical_reason: "policy hr-v1 rule",
            policy_version: "hr-v1",
            policy_restricted: null,
            impossible_under_policy: null,
          },
        ],
        detected_span_count: 3,
        detected_categories: ["employee_name", "cpf"],
      },
    });
  }

  it("uses the pt-BR category labels, not the raw identifiers", () => {
    render(<ResultScreen execute={withCategories()} health={{ status: "loading" }} onRestart={vi.fn()} compareError={null} onCompareStrategies={vi.fn()} onViewTechnicalDetails={vi.fn()} />);

    expect(screen.getByText(copy.categories.labels.employee_name, { exact: false })).toBeInTheDocument();
    expect(screen.getByText(copy.categories.labels.cpf, { exact: false })).toBeInTheDocument();
    expect(screen.queryByText(/employee_name/)).not.toBeInTheDocument();
  });
});

/**
 * T21 requires FakeProvider to be clearly distinguishable from a real
 * provider. Before this, `health: HealthResponse | null` conflated "still
 * loading" with "the check failed", and the failed case rendered nothing at
 * all -- so an unreachable `/health` silently produced a screen that looked
 * exactly like a verified real-provider run.
 */
describe("ResultScreen -- the provider mode when /health could not be checked", () => {
  it("says the mode could not be verified instead of omitting the indication", () => {
    render(
      <ResultScreen
        execute={execute()}
        health={{ status: "unavailable" }}
        onRestart={vi.fn()}
        compareError={null}
        onCompareStrategies={vi.fn()}
        onViewTechnicalDetails={vi.fn()}
      />,
    );

    expect(screen.getByText(copy.provider.modeUnverifiedLabel)).toBeInTheDocument();
  });

  it("does not claim the deterministic demo provider when the check failed", () => {
    render(
      <ResultScreen
        execute={execute()}
        health={{ status: "unavailable" }}
        onRestart={vi.fn()}
        compareError={null}
        onCompareStrategies={vi.fn()}
        onViewTechnicalDetails={vi.fn()}
      />,
    );

    expect(screen.queryByText(copy.provider.deterministicDemoLabel)).not.toBeInTheDocument();
  });

  it("does not show the unverified notice once health has actually answered", () => {
    render(<ResultScreen execute={execute()} health={healthState(true)} onRestart={vi.fn()} compareError={null} onCompareStrategies={vi.fn()} onViewTechnicalDetails={vi.fn()} />);

    expect(screen.queryByText(copy.provider.modeUnverifiedLabel)).not.toBeInTheDocument();
    expect(screen.getByText(copy.provider.deterministicDemoLabel)).toBeInTheDocument();
  });
});

/**
 * T21 second slice: the "Comparar estratégias" entry point. It is a
 * secondary action (never presented as the primary/only outcome of a
 * result) and it is discoverable without any prior knowledge of B0-B4.
 */
describe("ResultScreen -- Comparar estratégias entry point", () => {
  it("renders a Comparar estratégias action on every result, including blocked/failed ones", () => {
    render(
      <ResultScreen
        execute={execute()}
        health={{ status: "loading" }}
        onRestart={vi.fn()}
        compareError={null}
        onCompareStrategies={vi.fn()}
        onViewTechnicalDetails={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: copy.buttons.compareStrategies })).toBeInTheDocument();
  });

  it("calls onCompareStrategies when clicked -- it never calls executeDisclosure itself", async () => {
    const onCompareStrategies = vi.fn();
    render(
      <ResultScreen
        execute={execute()}
        health={{ status: "loading" }}
        onRestart={vi.fn()}
        compareError={null}
        onCompareStrategies={onCompareStrategies}
        onViewTechnicalDetails={vi.fn()}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: copy.buttons.compareStrategies }));

    expect(onCompareStrategies).toHaveBeenCalledTimes(1);
  });

  it("shows a generic error when a comparison request failed, never a fragment of a rejected response", () => {
    render(
      <ResultScreen
        execute={execute()}
        health={{ status: "loading" }}
        onRestart={vi.fn()}
        compareError={{ message: copy.errors.generic, kind: null, fields: null }}
        onCompareStrategies={vi.fn()}
        onViewTechnicalDetails={vi.fn()}
      />,
    );

    expect(screen.getByText(copy.errors.generic)).toBeInTheDocument();
  });

  it("shows no comparison error by default", () => {
    render(
      <ResultScreen
        execute={execute()}
        health={{ status: "loading" }}
        onRestart={vi.fn()}
        compareError={null}
        onCompareStrategies={vi.fn()}
        onViewTechnicalDetails={vi.fn()}
      />,
    );

    expect(screen.queryByText(copy.errors.generic)).not.toBeInTheDocument();
  });
});

/**
 * T21 third slice: the "Ver detalhes técnicos" entry point. Same posture as
 * "Comparar estratégias" above -- always offered, never gated on a
 * successful outcome, since the point is explaining what actually ran.
 */
describe("ResultScreen -- Ver detalhes técnicos entry point", () => {
  it("renders a Ver detalhes técnicos action on every result", () => {
    render(
      <ResultScreen
        execute={execute()}
        health={{ status: "loading" }}
        onRestart={vi.fn()}
        compareError={null}
        onCompareStrategies={vi.fn()}
        onViewTechnicalDetails={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: copy.buttons.viewTechnicalDetails })).toBeInTheDocument();
  });

  it("calls onViewTechnicalDetails when clicked -- it never calls executeDisclosure itself", async () => {
    const onViewTechnicalDetails = vi.fn();
    render(
      <ResultScreen
        execute={execute()}
        health={{ status: "loading" }}
        onRestart={vi.fn()}
        compareError={null}
        onCompareStrategies={vi.fn()}
        onViewTechnicalDetails={onViewTechnicalDetails}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: copy.buttons.viewTechnicalDetails }));

    expect(onViewTechnicalDetails).toHaveBeenCalledTimes(1);
  });
});

describe("ResultScreen -- switches to English (T21 fourth slice)", () => {
  it("renders English headings, path labels, category labels, and buttons when en is active", async () => {
    const executeWithCategory = execute({
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
            technical_reason: "policy hr-v1 rule",
            policy_version: "hr-v1",
            policy_restricted: null,
            impossible_under_policy: null,
          },
        ],
        detected_span_count: 1,
        detected_categories: ["employee_name"],
      },
    });
    await renderWithLocale(
      <ResultScreen
        execute={executeWithCategory}
        health={healthState(true)}
        onRestart={vi.fn()}
        compareError={{ message: en.errors.generic, kind: null, fields: null }}
        onCompareStrategies={vi.fn()}
        onViewTechnicalDetails={vi.fn()}
      />,
      "en",
    );

    expect(screen.getByRole("heading", { name: en.result.heading })).toBeInTheDocument();
    expect(screen.getByText(en.result.pathProvider)).toBeInTheDocument();
    expect(screen.getByText(en.provider.deterministicDemoLabel)).toBeInTheDocument();
    expect(screen.getByText(en.categories.labels.employee_name, { exact: false })).toBeInTheDocument();
    expect(screen.getByText(en.errors.generic)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: en.buttons.compareStrategies })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: en.buttons.viewTechnicalDetails })).toBeInTheDocument();
    expect(screen.queryByText(copy.result.heading)).not.toBeInTheDocument();
  });
});

describe("ResultScreen -- Vault Explorer gating (T29 / issue #72)", () => {
  const defaultProps = {
    health: { status: "loading" as const },
    onRestart: vi.fn(),
    compareError: null,
    onCompareStrategies: vi.fn(),
    onViewTechnicalDetails: vi.fn(),
  };

  it("is absent by default (demoVaultExplorerEnabled defaults to false) and makes no fetch call", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    render(<ResultScreen execute={execute()} {...defaultProps} />);

    expect(screen.queryByText(copy.vaultExplorerPanel.heading)).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("is absent when the feature is disabled even though a token is present", () => {
    render(
      <ResultScreen
        execute={execute()}
        {...defaultProps}
        demoVaultExplorerEnabled={false}
        vaultExplorerToken="vx1.token"
      />,
    );

    expect(screen.queryByText(copy.vaultExplorerPanel.heading)).not.toBeInTheDocument();
  });

  it("renders the panel heading when the feature is enabled, regardless of token", () => {
    render(
      <ResultScreen
        execute={execute()}
        {...defaultProps}
        demoVaultExplorerEnabled={true}
        vaultExplorerToken={null}
      />,
    );

    expect(screen.getByText(copy.vaultExplorerPanel.heading)).toBeInTheDocument();
    expect(screen.getByText(copy.vaultExplorerPanel.unavailableForDecision)).toBeInTheDocument();
  });
});
