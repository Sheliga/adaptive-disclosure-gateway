import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { CompareResponse, StrategyComparisonEntry } from "@/lib/contracts";
import { copy } from "@/lib/copy";

import { ComparisonScreen } from "./ComparisonScreen";

function entry(overrides: Partial<StrategyComparisonEntry> = {}): StrategyComparisonEntry {
  return {
    strategy: "b1",
    treatment: "static_sanitization",
    recommended: false,
    unsafe_control_baseline: false,
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
    external_payload: "PAYLOAD_MARKER_XYZ",
    payload_byte_count: 19,
    ...overrides,
  };
}

function comparison(entries: StrategyComparisonEntry[]): CompareResponse {
  return {
    contract_version: "t20-application-api-v1",
    entries,
    governance: {
      domain: "hr",
      purpose: "team_summary",
      policy_version: "hr-v1",
      provider_class: "FakeProvider",
      requester_role: null,
      requested_pseudonym_scope: "session",
    },
    provider_mode: { provider_class: "FakeProvider" },
  };
}

function fiveCanonicalEntries(): StrategyComparisonEntry[] {
  return [
    entry({ strategy: "b0", treatment: "direct", unsafe_control_baseline: true, external_payload: "PAYLOAD_B0" }),
    entry({ strategy: "b1", treatment: "static_sanitization", external_payload: "PAYLOAD_B1" }),
    entry({ strategy: "b2", treatment: "reversible_pseudonymization", external_payload: "PAYLOAD_B2" }),
    entry({ strategy: "b3", treatment: "task_aware", external_payload: "PAYLOAD_B3" }),
    entry({ strategy: "b4", treatment: "policy_governed", recommended: true, external_payload: "PAYLOAD_B4" }),
  ];
}

describe("ComparisonScreen -- teaches before showing codes", () => {
  it("renders the heading and the mandatory simulation notice", () => {
    render(<ComparisonScreen comparison={comparison(fiveCanonicalEntries())} onBack={vi.fn()} />);

    expect(screen.getByRole("heading", { name: copy.comparison.heading })).toBeInTheDocument();
    expect(screen.getByText(copy.comparison.simulationNotice)).toBeInTheDocument();
  });

  it("renders exactly five strategies for a five-entry comparison, in the order the API returned them", () => {
    render(<ComparisonScreen comparison={comparison(fiveCanonicalEntries())} onBack={vi.fn()} />);

    const names = fiveCanonicalEntries().map((e) => copy.treatments[e.strategy].name);
    const headings = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);

    // Every treatment name appears, and in the same relative order as the
    // entries array -- the component must never re-sort what the API sent.
    const positions = names.map((name) => headings.findIndex((h) => h?.includes(name)));
    expect(positions.every((p) => p >= 0)).toBe(true);
    expect(positions).toEqual([...positions].sort((a, b) => a - b));
  });

  it("shows the human treatment name, not the raw strategy code, as the visible headline", () => {
    render(<ComparisonScreen comparison={comparison([entry({ strategy: "b1" })])} onBack={vi.fn()} />);

    expect(screen.getByText(copy.treatments.b1.name)).toBeInTheDocument();
  });
});

describe("ComparisonScreen -- B0 warning is derived from unsafe_control_baseline, never from strategy code", () => {
  it("shows the unsafe-control warning for a b0 entry with the flag true", () => {
    render(
      <ComparisonScreen
        comparison={comparison([entry({ strategy: "b0", unsafe_control_baseline: true })])}
        onBack={vi.fn()}
      />,
    );

    expect(screen.getByText(copy.comparison.unsafeControlHeading)).toBeInTheDocument();
  });

  it("shows the unsafe-control warning for a NON-b0 entry when the flag is true", () => {
    // Pins T21/#29's requirement directly: the warning must come from the
    // flag, not from a hardcoded `strategy === "b0"` check.
    render(
      <ComparisonScreen
        comparison={comparison([entry({ strategy: "b2", unsafe_control_baseline: true })])}
        onBack={vi.fn()}
      />,
    );

    expect(screen.getByText(copy.comparison.unsafeControlHeading)).toBeInTheDocument();
  });

  it("does NOT show the unsafe-control warning for a b0 entry when the flag is false", () => {
    render(
      <ComparisonScreen
        comparison={comparison([entry({ strategy: "b0", unsafe_control_baseline: false })])}
        onBack={vi.fn()}
      />,
    );

    expect(screen.queryByText(copy.comparison.unsafeControlHeading)).not.toBeInTheDocument();
  });

  it("does not show the warning for any entry when no entry carries the flag", () => {
    render(<ComparisonScreen comparison={comparison(fiveCanonicalEntries().slice(1))} onBack={vi.fn()} />);

    expect(screen.queryByText(copy.comparison.unsafeControlHeading)).not.toBeInTheDocument();
  });
});

describe("ComparisonScreen -- recommended is product configuration, never a ranking", () => {
  it("shows the recommended badge text for the recommended entry", () => {
    render(
      <ComparisonScreen
        comparison={comparison([entry({ strategy: "b4", recommended: true })])}
        onBack={vi.fn()}
      />,
    );

    expect(screen.getByText(copy.comparison.recommendedBadge)).toBeInTheDocument();
  });

  it("never renders ranking/scoring/winner language anywhere on the screen", () => {
    render(<ComparisonScreen comparison={comparison(fiveCanonicalEntries())} onBack={vi.fn()} />);

    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/melhor|mais segura|vencedor|ranking|pontuação|estrela|score/i);
  });
});

describe("ComparisonScreen -- external_payload stays out of the tree until explicitly opened", () => {
  it("does not render any entry's payload by default", () => {
    render(<ComparisonScreen comparison={comparison(fiveCanonicalEntries())} onBack={vi.fn()} />);

    for (const marker of ["PAYLOAD_B0", "PAYLOAD_B1", "PAYLOAD_B2", "PAYLOAD_B3", "PAYLOAD_B4"]) {
      expect(screen.queryByText(marker)).not.toBeInTheDocument();
    }
  });

  it("reveals only the payload for the entry whose toggle was opened", async () => {
    render(<ComparisonScreen comparison={comparison(fiveCanonicalEntries())} onBack={vi.fn()} />);

    const toggles = screen.getAllByText(copy.comparison.showPayloadToggle);
    await userEvent.click(toggles[0]); // the b0 entry, first in canonical order

    expect(screen.getByText("PAYLOAD_B0")).toBeInTheDocument();
    expect(screen.queryByText("PAYLOAD_B1")).not.toBeInTheDocument();
  });

  it("shows explicit unsafe-control context before revealing the b0 payload", async () => {
    render(
      <ComparisonScreen
        comparison={comparison([entry({ strategy: "b0", unsafe_control_baseline: true, external_payload: "PAYLOAD_B0" })])}
        onBack={vi.fn()}
      />,
    );

    await userEvent.click(screen.getByText(copy.comparison.showPayloadToggle));

    expect(screen.getByText(copy.comparison.unsafeControlPayloadContext)).toBeInTheDocument();
    expect(screen.getByText("PAYLOAD_B0")).toBeInTheDocument();
  });
});

describe("ComparisonScreen -- what stays local vs what crosses the trust boundary", () => {
  it("splits categories using crosses_trust_boundary, reusing the same category presentation as Review/Result", () => {
    const withBothSides = entry({
      strategy: "b3",
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
            technical_reason: "x",
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
            technical_reason: "x",
            policy_version: "hr-v1",
            policy_restricted: null,
            impossible_under_policy: null,
          },
        ],
        detected_span_count: 2,
        detected_categories: ["employee_name", "cpf"],
      },
    });
    render(<ComparisonScreen comparison={comparison([withBothSides])} onBack={vi.fn()} />);

    expect(screen.getByText(copy.categories.labels.employee_name, { exact: false })).toBeInTheDocument();
    expect(screen.getByText(copy.categories.labels.cpf, { exact: false })).toBeInTheDocument();
    expect(screen.queryByText(/employee_name/)).not.toBeInTheDocument();
  });
});

describe("ComparisonScreen -- technical identifiers are secondary/expandable, not headline text", () => {
  it("shows the raw strategy/treatment codes only inside the technical-details toggle", () => {
    render(<ComparisonScreen comparison={comparison([entry({ strategy: "b1", treatment: "static_sanitization" })])} onBack={vi.fn()} />);

    // Not visible before opening any technical-details disclosure.
    expect(screen.queryByText("static_sanitization")).not.toBeInTheDocument();
  });
});

describe("ComparisonScreen -- navigation back to Result", () => {
  it("calls onBack when the back-to-result action is used", async () => {
    const onBack = vi.fn();
    render(<ComparisonScreen comparison={comparison(fiveCanonicalEntries())} onBack={onBack} />);

    await userEvent.click(screen.getByRole("button", { name: copy.comparison.backToResult }));

    expect(onBack).toHaveBeenCalledTimes(1);
  });
});
