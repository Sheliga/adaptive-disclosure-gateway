import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithLocale } from "@/i18n/renderWithLocale";
import type { DisclosureInspection, ExecuteResponse, HealthResponse } from "@/lib/contracts";
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
  it("renders the final answer directly, and the trust-boundary path once the 'entender o que aconteceu' disclosure is opened", async () => {
    const e = execute();
    render(<ResultScreen execute={e} health={{ status: "loading" }} onRestart={vi.fn()} compareError={null} onCompareStrategies={vi.fn()} onViewTechnicalDetails={vi.fn()} />);

    expect(screen.getByText(e.final_answer as string)).toBeInTheDocument();
    expect(screen.queryByText(copy.result.pathProvider)).not.toBeInTheDocument();

    await userEvent.click(screen.getByText(copy.result.whatHappenedToggle));

    expect(screen.getAllByText(copy.result.pathLocal).length).toBe(2);
    expect(screen.getByText(copy.result.pathProvider)).toBeInTheDocument();
  });
});

/**
 * T30 / issue #82: the result hierarchy must read, in DOM order, the final
 * answer -> the protections summary -> "entender o que aconteceu" ->
 * the research surface ("Comparar estratégias experimentais") -> the
 * technical/audit surface ("Ver detalhes técnicos") -> restart. This can
 * fail from a real defect: putting technical metadata above the answer, or
 * losing the explicit research/technical framing headings.
 */
describe("ResultScreen -- hierarchy order (T30)", () => {
  it("orders answer -> protections -> entender o que aconteceu -> research -> technical -> restart", () => {
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

    const answer = screen.getByText("Esta é a resposta final reconstruída.");
    const protections = screen.getByText(copy.result.protectionsAppliedHeading);
    const whatHappened = screen.getByText(copy.result.whatHappenedToggle);
    const research = screen.getByRole("heading", { name: copy.result.researchHeading });
    const technical = screen.getByRole("heading", { name: copy.result.technicalToolsHeading });
    const restart = screen.getByRole("button", { name: copy.result.restart });

    const ordered = [answer, protections, whatHappened, research, technical, restart];
    for (let i = 0; i < ordered.length - 1; i += 1) {
      expect(ordered[i].compareDocumentPosition(ordered[i + 1]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    }
  });

  it("groups Comparar estratégias under the research heading, and Ver detalhes técnicos under the technical heading", () => {
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

    const research = screen.getByRole("heading", { name: copy.result.researchHeading });
    const compareButton = screen.getByRole("button", { name: copy.buttons.compareStrategies });
    expect(research.compareDocumentPosition(compareButton) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    const technical = screen.getByRole("heading", { name: copy.result.technicalToolsHeading });
    const technicalButton = screen.getByRole("button", { name: copy.buttons.viewTechnicalDetails });
    expect(technical.compareDocumentPosition(technicalButton) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});

/**
 * T30 / issue #82 review follow-up (Finding 1): the protections summary
 * must be a TRUTHFUL, data-derived breakdown -- never a single headline
 * that sums `occurrence_count` across every category regardless of
 * outcome (that folded `preserved`, sent-unchanged data, and even unknown
 * outcomes into a "protected" count), and never an invented reconstruction
 * COUNT the API does not report (`ReconstructionStage` only has
 * `attempted`/`reconstructed_hash`/`changed_from_provider_response`, no
 * count of successful reconstructions). Each case below fails against the
 * pre-fix implementation.
 */
describe("ResultScreen -- protections breakdown (T30 review follow-up)", () => {
  function categoriesFor(occurrences: { outcome: string; action: string; count: number }[]) {
    return occurrences.map(({ outcome, action, count }, index) => ({
      category: `cat_${index}`,
      outcome,
      action,
      crosses_trust_boundary: outcome === "pseudonymized",
      occurrence_count: count,
      required_for_task: null,
      technical_reason: "rule",
      policy_version: null,
      policy_restricted: null,
      impossible_under_policy: null,
    }));
  }

  it("shows a per-action breakdown built only from occurrence_count, in canonical order", () => {
    const e = execute({
      summary: {
        status: "allowed",
        categories: categoriesFor([
          { outcome: "removed", action: "remove", count: 2 },
          { outcome: "pseudonymized", action: "pseudonymize", count: 3 },
          { outcome: "generalized", action: "generalize", count: 1 },
          { outcome: "preserved", action: "preserve", count: 2 },
        ]),
        detected_span_count: 8,
        detected_categories: ["cat_0", "cat_1", "cat_2", "cat_3"],
      },
      reconstruction: { attempted: true, reconstructed_hash: "x", changed_from_provider_response: false },
    });

    render(
      <ResultScreen execute={e} health={{ status: "loading" }} onRestart={vi.fn()} compareError={null} onCompareStrategies={vi.fn()} onViewTechnicalDetails={vi.fn()} />,
    );

    const expected = [
      `${copy.outcomes.removed.label}: 2`,
      `${copy.outcomes.pseudonymized.label}: 3`,
      `${copy.outcomes.generalized.label}: 1`,
      `${copy.outcomes.preserved.label}: 2`,
    ].join(" · ");
    expect(screen.getByText(expected)).toBeInTheDocument();
  });

  it("never renders a 'protegido(s)' claim when every category is preserved (sent unchanged)", () => {
    const e = execute({
      summary: {
        status: "allowed",
        categories: categoriesFor([{ outcome: "preserved", action: "preserve", count: 3 }]),
        detected_span_count: 3,
        detected_categories: ["cat_0"],
      },
    });

    render(
      <ResultScreen execute={e} health={{ status: "loading" }} onRestart={vi.fn()} compareError={null} onCompareStrategies={vi.fn()} onViewTechnicalDetails={vi.fn()} />,
    );

    expect(screen.queryByText(/protegid[oa]s?/i)).not.toBeInTheDocument();
    expect(screen.getByText(`${copy.outcomes.preserved.label}: 3`)).toBeInTheDocument();
  });

  it("counts an unknown outcome under its own unknown bucket, never folded into a protective group", () => {
    const e = execute({
      summary: {
        status: "allowed",
        categories: categoriesFor([
          { outcome: "removed", action: "remove", count: 1 },
          { outcome: "a_future_outcome_this_ui_does_not_know", action: "mystery", count: 5 },
        ]),
        detected_span_count: 6,
        detected_categories: ["cat_0", "cat_1"],
      },
    });

    render(
      <ResultScreen execute={e} health={{ status: "loading" }} onRestart={vi.fn()} compareError={null} onCompareStrategies={vi.fn()} onViewTechnicalDetails={vi.fn()} />,
    );

    const expected = [`${copy.outcomes.removed.label}: 1`, `${copy.outcomes.unknown.label}: 5`].join(" · ");
    expect(screen.getByText(expected)).toBeInTheDocument();
    expect(screen.queryByText(/protegid[oa]s?:\s*5/i)).not.toBeInTheDocument();
  });

  it("shows the reconstruction note only when reconstruction was attempted AND the answer actually changed", () => {
    const e = execute({
      summary: {
        status: "allowed",
        categories: categoriesFor([{ outcome: "pseudonymized", action: "pseudonymize", count: 2 }]),
        detected_span_count: 2,
        detected_categories: ["cat_0"],
      },
      reconstruction: { attempted: true, reconstructed_hash: "x", changed_from_provider_response: true },
    });

    render(
      <ResultScreen execute={e} health={{ status: "loading" }} onRestart={vi.fn()} compareError={null} onCompareStrategies={vi.fn()} onViewTechnicalDetails={vi.fn()} />,
    );

    expect(screen.getByText(copy.result.reconstructionApplied)).toBeInTheDocument();
  });

  it.each([
    [false, false as boolean | null],
    [true, false as boolean | null],
    [true, null as boolean | null],
  ])(
    "shows no reconstruction line and no numeric 'reconstruídos' count (attempted=%s, changed=%s)",
    (attempted, changed_from_provider_response) => {
      const e = execute({
        summary: {
          status: "allowed",
          categories: categoriesFor([{ outcome: "pseudonymized", action: "pseudonymize", count: 2 }]),
          detected_span_count: 2,
          detected_categories: ["cat_0"],
        },
        reconstruction: {
          attempted,
          reconstructed_hash: attempted ? "x" : null,
          changed_from_provider_response,
        },
      });

      render(
        <ResultScreen execute={e} health={{ status: "loading" }} onRestart={vi.fn()} compareError={null} onCompareStrategies={vi.fn()} onViewTechnicalDetails={vi.fn()} />,
      );

      expect(screen.queryByText(copy.result.reconstructionApplied)).not.toBeInTheDocument();
      expect(screen.queryByText(/reconstru[ií]dos?/i)).not.toBeInTheDocument();
    },
  );
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
    await userEvent.click(screen.getByText(en.result.whatHappenedToggle));
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

/**
 * T32.3 / #103: the Result recap answers "which transformation did this
 * answer come after?" from the preview ALREADY held in flow state (the
 * `inspection` prop) -- `ExecuteResponse` is not widened. Wording follows
 * `execute.provider`: nothing is ever said to have been sent when the
 * provider was not called, and a failed call is an attempt, not an answer.
 */
describe("ResultScreen -- before-sending recap (T32.3 / #103)", () => {
  const SEGMENTS = [
    { action: null, category: null, original: "Relatório de ", disclosed: "Relatório de " },
    { action: "pseudonymize", category: "employee_name", original: "Maria Silva", disclosed: "PESSOA_7f3a" },
    { action: null, category: null, original: ", salário ", disclosed: ", salário " },
    { action: "generalize", category: "salary", original: "R$ 8.500,00", disclosed: "R$ 5.000-10.000" },
    { action: "remove", category: "cpf", original: "123.456.789-00", disclosed: "" },
  ];
  const AVAILABLE: DisclosureInspection = { available: true, unavailable_reason: null, segments: SEGMENTS };
  const COUNT = copy.resultRecap.handledCount.replace("{n}", "3");

  function renderResult(e: ExecuteResponse, inspection?: DisclosureInspection | null) {
    return render(
      <ResultScreen
        execute={e}
        health={{ status: "loading" }}
        onRestart={vi.fn()}
        compareError={null}
        onCompareStrategies={vi.fn()}
        onViewTechnicalDetails={vi.fn()}
        inspection={inspection}
      />,
    );
  }

  function recap(): HTMLElement {
    return screen.getByTestId("result-recap");
  }

  it("success: a short visible recap with the count, and no technical detail", () => {
    renderResult(execute(), AVAILABLE);

    expect(within(recap()).getByRole("heading", { name: copy.resultRecap.heading })).toBeInTheDocument();
    expect(within(recap()).getByText(copy.resultRecap.sent)).toBeInTheDocument();
    expect(within(recap()).getByText(COUNT)).toBeInTheDocument();
    const text = recap().textContent ?? "";
    expect(text).not.toMatch(/\bb[0-4]\b/i);
    expect(text).not.toContain("recommended");
    expect(text).not.toContain("employee_name");
  });

  it("describes the transformation reviewed before sending using real provider state, distinct across called/failed/not-called, with no preview-was-exact-payload claim (#103 review, PR #108)", () => {
    renderResult(execute(), AVAILABLE);

    // Distinct copy per real `execute.provider` state (called success vs. the
    // failed/not-called messages verified below by the other tests in this
    // describe block) -- these three strings must never collapse to the same
    // wording.
    expect(copy.resultRecap.sent).not.toBe(copy.resultRecap.providerFailed);
    expect(copy.resultRecap.sent).not.toBe(copy.resultRecap.notSent);
    expect(copy.resultRecap.providerFailed).not.toBe(copy.resultRecap.notSent);

    expect(document.body.textContent).not.toMatch(/Exatamente esta representação/);
    expect(document.body.textContent).not.toMatch(/exatamente o que foi enviado/i);
  });

  /**
   * #103 round-2 review fix (PR #108): `resultRecap.sent` once unconditionally
   * said the answer was "reconstruída localmente" / "reconstructed locally".
   * `final_answer` may be the provider's response completely unchanged (see
   * `ReconstructionStage`); only `buildReconstructionNote` may state a
   * reconstruction happened, and only when `reconstruction.attempted &&
   * changed_from_provider_response === true`. The recap itself must never
   * make that claim, regardless of the reconstruction state -- so the whole
   * rendered page (recap included) carries no reconstruction wording when
   * that condition does not hold, even though the recap is shown.
   *
   * `final_answer` is overridden to plain, reconstruction-free text here:
   * the shared `execute()` fixture's default answer text itself contains
   * "reconstruída", which would otherwise make a body-text search for that
   * word meaningless.
   */
  it.each([
    ["not attempted", { attempted: false, reconstructed_hash: null, changed_from_provider_response: null }],
    ["attempted but unchanged", { attempted: true, reconstructed_hash: "x", changed_from_provider_response: false }],
  ] as const)(
    "reconstruction %s: the recap is shown, and no reconstruction claim appears anywhere on the page",
    (_label, reconstruction) => {
      const e = execute({ final_answer: "Esta é a resposta do provedor.", reconstruction });
      renderResult(e, AVAILABLE);

      expect(within(recap()).getByText(copy.resultRecap.sent)).toBeInTheDocument();
      expect(document.body.textContent).not.toMatch(/reconstru|restaur|restored/i);
      expect(screen.queryByText(copy.result.reconstructionApplied)).not.toBeInTheDocument();
    },
  );

  it("reconstruction attempted AND changed: the reconstruction claim comes only from result.reconstructionApplied, never from the recap itself", () => {
    const e = execute({
      final_answer: "Esta é a resposta do provedor.",
      // `reconstructionNote` only renders when `summary.categories` is
      // non-empty (see `buildProtectionsBreakdown`'s early return), so a
      // category is required here for `result.reconstructionApplied` to
      // have any chance of appearing at all.
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
            technical_reason: "r",
            policy_version: null,
            policy_restricted: null,
            impossible_under_policy: null,
          },
        ],
        detected_span_count: 1,
        detected_categories: ["employee_name"],
      },
      reconstruction: { attempted: true, reconstructed_hash: "x", changed_from_provider_response: true },
    });
    renderResult(e, AVAILABLE);

    expect(within(recap()).getByText(copy.resultRecap.sent)).toBeInTheDocument();
    expect(within(recap()).queryByText(/reconstru|restaur|restored/i)).not.toBeInTheDocument();
    expect(screen.getByText(copy.result.reconstructionApplied)).toBeInTheDocument();
  });

  it("counts transformations by segment.action, not by category occurrence counts", () => {
    const e = execute({
      summary: {
        status: "allowed",
        categories: [
          {
            category: "employee_name",
            outcome: "pseudonymized",
            action: "pseudonymize",
            crosses_trust_boundary: true,
            occurrence_count: 9,
            required_for_task: null,
            technical_reason: "r",
            policy_version: null,
            policy_restricted: null,
            impossible_under_policy: null,
          },
        ],
        detected_span_count: 9,
        detected_categories: ["employee_name"],
      },
    });
    renderResult(e, AVAILABLE);

    expect(within(recap()).getByText(COUNT)).toBeInTheDocument();
  });

  it("keeps the full before/after collapsed, out of the DOM, until asked for", async () => {
    renderResult(execute(), AVAILABLE);

    expect(screen.queryByText("PESSOA_7f3a")).not.toBeInTheDocument();
    expect(screen.queryByText("Maria Silva")).not.toBeInTheDocument();

    await userEvent.click(within(recap()).getByText(copy.resultRecap.seeBeforeAfter));

    expect(within(recap()).getByText("PESSOA_7f3a")).toBeInTheDocument();
    expect(within(recap()).getByText(copy.beforeAfter.disclosedHeadingApproved)).toBeInTheDocument();
  });

  it("sits right after the answer and before the protections summary", () => {
    renderResult(execute(), AVAILABLE);

    const answer = screen.getByText(copy.sectionHeadings.finalAnswer);
    const protections = screen.getByText(copy.result.protectionsAppliedHeading);
    expect(answer.compareDocumentPosition(recap()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(recap().compareDocumentPosition(protections) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("provider failure: says the call was attempted and failed, never that an answer came after it", () => {
    const e = execute({
      final_answer: null,
      provider: { ...execute().provider, called: true, failed: true, failure_kind: "timeout" },
    });
    renderResult(e, AVAILABLE);

    expect(within(recap()).getByText(copy.resultRecap.providerFailed)).toBeInTheDocument();
    expect(within(recap()).queryByText(copy.resultRecap.sent)).not.toBeInTheDocument();
  });

  it("provider not called: says nothing was sent, even when the preview had an available before/after", () => {
    const e = execute({
      final_answer: null,
      provider: { ...execute().provider, called: false, transmitted_bytes: null },
    });
    renderResult(e, AVAILABLE);

    expect(within(recap()).getByText(copy.resultRecap.notSent)).toBeInTheDocument();
    expect(within(recap()).queryByText(copy.resultRecap.sent)).not.toBeInTheDocument();
    expect(within(recap()).queryByText(copy.resultRecap.providerFailed)).not.toBeInTheDocument();
  });

  it("blocked: no metrics, no before/after, and no claim that anything was sent", () => {
    const e = execute({
      status: "blocked",
      final_answer: null,
      summary: { status: "blocked", categories: [], detected_span_count: 0, detected_categories: [] },
      provider: { ...execute().provider, called: false, transmitted_bytes: null },
    });
    renderResult(e, { available: false, unavailable_reason: "blocked", segments: [] });

    expect(within(recap()).getByText(copy.resultRecap.notSent)).toBeInTheDocument();
    expect(within(recap()).getByText(copy.beforeAfter.unavailableBlocked)).toBeInTheDocument();
    expect(within(recap()).queryByText(/\d/)).not.toBeInTheDocument();
    expect(within(recap()).queryByText(copy.resultRecap.seeBeforeAfter)).not.toBeInTheDocument();
    expect(within(recap()).queryByText(copy.resultRecap.sent)).not.toBeInTheDocument();
  });

  it("blocked at execute even though the provider flag says called: still never claims a send", () => {
    const e = execute({
      status: "blocked",
      final_answer: null,
      summary: { status: "blocked", categories: [], detected_span_count: 0, detected_categories: [] },
    });
    renderResult(e, AVAILABLE);

    expect(within(recap()).getByText(copy.resultRecap.notSent)).toBeInTheDocument();
    expect(within(recap()).queryByText(copy.resultRecap.sent)).not.toBeInTheDocument();
  });

  it("alignment_failed: plain message, no count and no before/after toggle", () => {
    renderResult(execute(), { available: false, unavailable_reason: "alignment_failed", segments: [] });

    expect(within(recap()).getByText(copy.beforeAfter.unavailableAlignmentFailed)).toBeInTheDocument();
    expect(within(recap()).queryByText(copy.resultRecap.seeBeforeAfter)).not.toBeInTheDocument();
    expect(recap().textContent).not.toMatch(/\d/);
  });

  it.each([null, undefined])("renders no recap at all when inspection is %s", (inspection) => {
    renderResult(execute(), inspection);

    expect(screen.queryByTestId("result-recap")).not.toBeInTheDocument();
  });

  it("renders the recap in English under the en locale", async () => {
    await renderWithLocale(
      <ResultScreen
        execute={execute()}
        health={{ status: "loading" }}
        onRestart={vi.fn()}
        compareError={null}
        onCompareStrategies={vi.fn()}
        onViewTechnicalDetails={vi.fn()}
        inspection={AVAILABLE}
      />,
      "en",
    );

    expect(screen.getByRole("heading", { name: en.resultRecap.heading })).toBeInTheDocument();
    expect(screen.getByText(en.resultRecap.sent)).toBeInTheDocument();
    expect(screen.getByText(en.resultRecap.handledCount.replace("{n}", "3"))).toBeInTheDocument();

    // #103 review fix (PR #108): no byte-identity claim with the preview.
    expect(document.body.textContent).not.toMatch(/Exactly this representation/);
  });
});
