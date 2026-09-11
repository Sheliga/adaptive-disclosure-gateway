import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithLocale } from "@/i18n/renderWithLocale";
import type { CategoryDisclosureSummary, PreviewResponse } from "@/lib/contracts";
import { copy } from "@/lib/copy";
import { en } from "@/lib/copy.en";

import { ReviewScreen } from "./ReviewScreen";

beforeEach(() => {
  window.localStorage.clear();
});

function category(overrides: Partial<CategoryDisclosureSummary>): CategoryDisclosureSummary {
  return {
    category: "employee_name",
    outcome: "removed",
    action: "remove",
    crosses_trust_boundary: false,
    occurrence_count: 1,
    required_for_task: null,
    technical_reason: "detected by rule X",
    policy_version: null,
    policy_restricted: null,
    impossible_under_policy: null,
    ...overrides,
  };
}

function preview(categories: CategoryDisclosureSummary[], status: "allowed" | "blocked" = "allowed"): PreviewResponse {
  return {
    contract_version: "t20-application-api-v1",
    summary: {
      status,
      categories,
      detected_span_count: categories.length,
      detected_categories: categories.map((c) => c.category),
    },
    external_payload: "exact payload text that would be sent",
    payload_byte_count: 37,
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
  };
}

describe("ReviewScreen -- local vs sent split follows crosses_trust_boundary", () => {
  it("groups a removed category with crosses_trust_boundary=false under 'what stays local'", () => {
    render(
      <ReviewScreen
        preview={preview([category({ category: "cpf", outcome: "removed", crosses_trust_boundary: false })])}
        executeError={null}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByText(copy.outcomes.protectedLocally.label)).toBeInTheDocument();
    expect(screen.queryByText(copy.outcomes.sentToProvider.label)).not.toBeInTheDocument();
  });

  it("follows the flag even when it disagrees with what the outcome code alone would suggest", () => {
    // "removed" naively reads as "never sent" -- but the flag says it
    // crossed the boundary (e.g. mentioned in a report sent externally),
    // and the flag must win.
    render(
      <ReviewScreen
        preview={preview([category({ category: "cpf", outcome: "removed", crosses_trust_boundary: true })])}
        executeError={null}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByText(copy.outcomes.sentToProvider.label)).toBeInTheDocument();
    expect(screen.queryByText(copy.outcomes.protectedLocally.label)).not.toBeInTheDocument();
  });

  it("follows the flag the other way too -- 'pseudonymized' but flagged as staying local", () => {
    render(
      <ReviewScreen
        preview={preview([
          category({ category: "email", outcome: "pseudonymized", crosses_trust_boundary: false }),
        ])}
        executeError={null}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByText(copy.outcomes.protectedLocally.label)).toBeInTheDocument();
    expect(screen.queryByText(copy.outcomes.sentToProvider.label)).not.toBeInTheDocument();
  });
});

describe("ReviewScreen -- unknown outcome fails closed", () => {
  it("never renders an unrecognized outcome as protected/local, regardless of section", () => {
    render(
      <ReviewScreen
        preview={preview([
          category({ category: "mystery", outcome: "quantum_redacted", crosses_trust_boundary: false }),
        ])}
        executeError={null}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );

    expect(screen.getByText(copy.outcomes.unknown.label)).toBeInTheDocument();
    expect(screen.queryByText(copy.outcomes.protectedLocally.label)).not.toBeInTheDocument();
    const boundaryTexts = screen.getAllByText(copy.outcomes.unknown.boundaryLabel);
    expect(boundaryTexts.length).toBeGreaterThan(0);
  });
});

describe("ReviewScreen -- external_payload is behind an explicit disclosure control", () => {
  it("is not in the document by default", () => {
    const p = preview([category({})]);
    render(<ReviewScreen preview={p} executeError={null} onConfirm={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.queryByText(p.external_payload)).not.toBeInTheDocument();
  });

  it("appears only after the disclosure control is opened", async () => {
    const p = preview([category({})]);
    render(<ReviewScreen preview={p} executeError={null} onConfirm={vi.fn()} onCancel={vi.fn()} />);

    await userEvent.click(screen.getByText(copy.review.showPayloadToggle));

    expect(await screen.findByText(p.external_payload)).toBeInTheDocument();
  });
});

describe("ReviewScreen -- blocked preview", () => {
  it("offers no continue/confirm action", () => {
    render(
      <ReviewScreen
        preview={preview([category({ outcome: "blocked" })], "blocked")}
        executeError={null}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.queryByRole("button", { name: copy.review.confirmSend })).not.toBeInTheDocument();
    expect(screen.getByText(copy.review.blockedHeading)).toBeInTheDocument();
  });

  it("never calls onConfirm since there is no button wired to it", () => {
    const onConfirm = vi.fn();
    render(
      <ReviewScreen
        preview={preview([], "blocked")}
        executeError={null}
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.queryByRole("button", { name: copy.review.confirmSend })).toBeNull();
    expect(onConfirm).not.toHaveBeenCalled();
  });
});

describe("ReviewScreen -- confirm/cancel wiring", () => {
  it("calls onConfirm when the confirm button is clicked (allowed preview)", async () => {
    const onConfirm = vi.fn();
    render(
      <ReviewScreen preview={preview([category({})])} executeError={null} onConfirm={onConfirm} onCancel={vi.fn()} />,
    );
    await userEvent.click(screen.getByRole("button", { name: copy.review.confirmSend }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("calls onCancel when the back button is clicked", async () => {
    const onCancel = vi.fn();
    render(
      <ReviewScreen preview={preview([category({})])} executeError={null} onConfirm={vi.fn()} onCancel={onCancel} />,
    );
    await userEvent.click(screen.getByRole("button", { name: copy.review.backToCompose }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("renders a retry-visible execute error without hiding the confirm action", () => {
    render(
      <ReviewScreen
        preview={preview([category({})])}
        executeError={{ message: "falha ao enviar", kind: null, fields: null }}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByText("falha ao enviar")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: copy.review.confirmSend })).toBeInTheDocument();
  });
});

/**
 * T21's novice-first rule (issue #29: "a reviewer unfamiliar with the
 * project can understand the purpose without external documentation"),
 * applied to the review step -- the one screen whose entire job is to be
 * understood before the user consents to send anything.
 *
 * The internal identifiers are NOT renamed anywhere: `category.category`
 * still carries `employee_name` verbatim from the API, and nothing about
 * the policy, corpus or contract changes. Only what the reviewer reads
 * changes. See `lib/categoryLabels.ts`.
 */
describe("ReviewScreen -- categories are presented in human language", () => {
  it("shows the pt-BR label instead of the raw identifier for a local category", () => {
    render(
      <ReviewScreen
        preview={preview([
          category({ category: "employee_name", outcome: "removed", crosses_trust_boundary: false }),
        ])}
        executeError={null}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );

    expect(screen.getByText(copy.categories.labels.employee_name)).toBeInTheDocument();
    expect(screen.queryByText("employee_name")).not.toBeInTheDocument();
  });

  it("shows the pt-BR label for a category that crossed the trust boundary too", () => {
    render(
      <ReviewScreen
        preview={preview([
          category({ category: "salary", outcome: "generalized", crosses_trust_boundary: true }),
        ])}
        executeError={null}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );

    expect(screen.getByText(copy.categories.labels.salary)).toBeInTheDocument();
    expect(screen.queryByText("salary")).not.toBeInTheDocument();
  });

  it("renders none of the HR corpus identifiers as a label anywhere on the screen", () => {
    const identifiers = ["employee_name", "cpf", "salary", "department", "medical_data"];
    render(
      <ReviewScreen
        preview={preview(
          identifiers.map((name) =>
            category({ category: name, outcome: "removed", crosses_trust_boundary: false }),
          ),
        )}
        executeError={null}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );

    for (const identifier of identifiers) {
      expect(screen.queryByText(identifier)).not.toBeInTheDocument();
      expect(
        screen.getByText(copy.categories.labels[identifier as keyof typeof copy.categories.labels]),
      ).toBeInTheDocument();
    }
  });

  it("labels an unrecognized category as unrecognized, never with an invented meaning", () => {
    render(
      <ReviewScreen
        preview={preview([
          category({ category: "shoe_size", outcome: "removed", crosses_trust_boundary: false }),
        ])}
        executeError={null}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );

    expect(screen.getByText(copy.categories.unrecognized)).toBeInTheDocument();
    // The raw identifier is still reachable as a technical detail -- the
    // reviewer needs to be able to report exactly what the API sent.
    expect(screen.getByText("shoe_size")).toBeInTheDocument();
  });
});

describe("ReviewScreen -- switches to English (T21 fourth slice)", () => {
  it("renders English category labels and outcome/boundary copy when en is active", async () => {
    await renderWithLocale(
      <ReviewScreen
        preview={preview([
          category({ category: "employee_name", outcome: "removed", crosses_trust_boundary: false }),
        ])}
        executeError={null}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
      "en",
    );

    expect(screen.getByRole("heading", { name: en.review.heading })).toBeInTheDocument();
    expect(screen.getByText(en.categories.labels.employee_name)).toBeInTheDocument();
    expect(screen.getByText(en.outcomes.protectedLocally.label)).toBeInTheDocument();
    expect(screen.getByText(en.outcomes.removed.label)).toBeInTheDocument();
    expect(screen.queryByText(copy.review.heading)).not.toBeInTheDocument();
    // The technical identifier itself never translates.
    expect(screen.queryByText("employee_name")).not.toBeInTheDocument(); // still not shown as a label
  });

  it("reveals the payload behind the English toggle text", async () => {
    const p = preview([category({})]);
    await renderWithLocale(
      <ReviewScreen preview={p} executeError={null} onConfirm={vi.fn()} onCancel={vi.fn()} />,
      "en",
    );

    await userEvent.click(screen.getByText(en.review.showPayloadToggle));

    expect(await screen.findByText(p.external_payload)).toBeInTheDocument();
  });
});
