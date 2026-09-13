import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { CategoryDisclosureSummary, DisclosureInspection, InspectionSegment } from "@/lib/contracts";
import { copy } from "@/lib/copy";

import { DisclosureInspector } from "./DisclosureInspector";

function segment(overrides: Partial<InspectionSegment> = {}): InspectionSegment {
  return { action: null, category: null, original: "", disclosed: "", ...overrides };
}

function category(overrides: Partial<CategoryDisclosureSummary> = {}): CategoryDisclosureSummary {
  return {
    category: "employee_name",
    outcome: "pseudonymized",
    action: "pseudonymize",
    crosses_trust_boundary: true,
    occurrence_count: 1,
    required_for_task: null,
    technical_reason: "detected by rule X",
    policy_version: "hr-v1",
    policy_restricted: null,
    impossible_under_policy: null,
    ...overrides,
  };
}

function available(segments: InspectionSegment[]): DisclosureInspection {
  return { available: true, unavailable_reason: null, segments };
}

async function openInspector() {
  await userEvent.click(screen.getByText(copy.disclosureInspector.toggleLabel));
}

describe("DisclosureInspector -- collapsed by default, content absent from DOM until opened", () => {
  it("does not render column headings until the disclosure is opened", () => {
    render(
      <DisclosureInspector
        inspection={available([segment({ original: "hello", disclosed: "hello" })])}
        categories={[]}
        treatment="b0"
        strategy="b0"
      />,
    );

    expect(screen.queryByText(copy.disclosureInspector.originalColumnHeading)).not.toBeInTheDocument();
    expect(screen.getByText(copy.disclosureInspector.toggleLabel)).toBeInTheDocument();
  });

  it("renders the columns once opened", async () => {
    render(
      <DisclosureInspector
        inspection={available([segment({ original: "hello", disclosed: "hello" })])}
        categories={[]}
        treatment="b0"
        strategy="b0"
      />,
    );

    await openInspector();

    expect(screen.getByText(copy.disclosureInspector.originalColumnHeading)).toBeInTheDocument();
    expect(screen.getByText(copy.disclosureInspector.disclosedColumnHeading)).toBeInTheDocument();
  });
});

describe("DisclosureInspector -- segments render in order on both sides", () => {
  it("shows untouched text unchanged and transformed segments on both columns in order", async () => {
    const segments = [
      segment({ original: "Prezado ", disclosed: "Prezado " }),
      segment({
        action: "pseudonymize",
        category: "employee_name",
        original: "João Silva",
        disclosed: "PSEUDO-a1b2",
      }),
      segment({ original: ", segue o relatório.", disclosed: ", segue o relatório." }),
    ];
    render(
      <DisclosureInspector inspection={available(segments)} categories={[]} treatment="b2" strategy="b2" />,
    );

    await openInspector();

    const originalColumn = screen.getByTestId("inspector-original-column");
    const disclosedColumn = screen.getByTestId("inspector-disclosed-column");

    expect(within(originalColumn).getByText("João Silva")).toBeInTheDocument();
    expect(within(disclosedColumn).getByText("PSEUDO-a1b2")).toBeInTheDocument();
    expect(originalColumn.textContent).toBe("Prezado João Silva, segue o relatório.");
    expect(disclosedColumn.textContent).toBe("Prezado PSEUDO-a1b2, segue o relatório.");
  });

  it("attaches the right badge/category to each occurrence when identical text repeats with different actions/categories", async () => {
    const segments = [
      segment({ action: "pseudonymize", category: "employee_name", original: "Maria", disclosed: "PSEUDO-1" }),
      segment({ original: " trabalha com ", disclosed: " trabalha com " }),
      segment({ action: "remove", category: "medical_data", original: "Maria", disclosed: "" }),
    ];
    render(
      <DisclosureInspector inspection={available(segments)} categories={[]} treatment="b2" strategy="b2" />,
    );
    await openInspector();

    const originalColumn = screen.getByTestId("inspector-original-column");
    const marias = within(originalColumn).getAllByText("Maria");
    expect(marias).toHaveLength(2);

    await userEvent.click(marias[0]);
    expect(screen.getByText(copy.categories.labels.employee_name)).toBeInTheDocument();

    await userEvent.click(marias[1]);
    expect(screen.getByText(copy.categories.labels.medical_data)).toBeInTheDocument();
  });

  it("preserves accents, emoji, combining marks, and multiline text exactly", async () => {
    const originalMultiline = "café ́\ncom açúcar\r\n😀 fim";
    const segments = [segment({ original: originalMultiline, disclosed: originalMultiline })];
    render(
      <DisclosureInspector inspection={available(segments)} categories={[]} treatment="b0" strategy="b0" />,
    );

    await openInspector();

    const originalColumn = screen.getByTestId("inspector-original-column");
    const disclosedColumn = screen.getByTestId("inspector-disclosed-column");
    expect(originalColumn.textContent).toBe(originalMultiline);
    expect(disclosedColumn.textContent).toBe(originalMultiline);
  });

  it("shows an explicit removed marker on the disclosed side for a removed segment, without corrupting the original side", async () => {
    const segments = [segment({ action: "remove", category: "cpf", original: "123.456.789-00", disclosed: "" })];
    render(
      <DisclosureInspector inspection={available(segments)} categories={[]} treatment="b1" strategy="b1" />,
    );

    await openInspector();

    const originalColumn = screen.getByTestId("inspector-original-column");
    const disclosedColumn = screen.getByTestId("inspector-disclosed-column");
    expect(originalColumn.textContent).toBe("123.456.789-00");
    expect(disclosedColumn.textContent).toBe(copy.inspectionActions.removedMarker);
  });
});

describe("DisclosureInspector -- legend shows four distinct visible action labels", () => {
  it("renders distinct text labels for preserve/remove/generalize/pseudonymize", async () => {
    render(
      <DisclosureInspector
        inspection={available([segment({ original: "x", disclosed: "x" })])}
        categories={[]}
        treatment="b4"
        strategy="b4"
      />,
    );

    await openInspector();

    expect(screen.getByText(copy.inspectionActions.preserve.label)).toBeInTheDocument();
    expect(screen.getByText(copy.inspectionActions.pseudonymize.label)).toBeInTheDocument();
    expect(screen.getByText(copy.inspectionActions.generalize.label)).toBeInTheDocument();
    expect(screen.getByText(copy.inspectionActions.remove.label)).toBeInTheDocument();

    const labels = [
      copy.inspectionActions.preserve.label,
      copy.inspectionActions.pseudonymize.label,
      copy.inspectionActions.generalize.label,
      copy.inspectionActions.remove.label,
    ];
    expect(new Set(labels).size).toBe(4);
  });
});

describe("DisclosureInspector -- detail panel", () => {
  it("shows action, category, reason, treatment/strategy and ordinal for the selected segment", async () => {
    const segments = [
      segment({ original: "Contrato ", disclosed: "Contrato " }),
      segment({
        action: "generalize",
        category: "salary",
        original: "R$ 12.345,67",
        disclosed: "faixa salarial média",
      }),
    ];
    render(
      <DisclosureInspector
        inspection={available(segments)}
        categories={[category({ category: "salary", outcome: "generalized", action: "generalize", technical_reason: "policy hr-v2 rule 3" })]}
        treatment="b4"
        strategy="recommended"
      />,
    );
    await openInspector();

    await userEvent.click(screen.getByText("R$ 12.345,67"));

    const detailPanel = screen.getByTestId("inspector-detail-panel");
    expect(within(detailPanel).getByText(copy.inspectionActions.generalize.label)).toBeInTheDocument();
    expect(within(detailPanel).getByText(copy.categories.labels.salary)).toBeInTheDocument();
    expect(within(detailPanel).getByText("policy hr-v2 rule 3")).toBeInTheDocument();
    expect(within(detailPanel).getByText("b4")).toBeInTheDocument();
    expect(within(detailPanel).getByText("recommended")).toBeInTheDocument();
    expect(within(detailPanel).getByText(copy.treatments.b4.name)).toBeInTheDocument();
    expect(within(detailPanel).getByText("Item 1 de 1")).toBeInTheDocument();
  });

  it("shows an explicit not-available reason when no matching category summary exists", async () => {
    const segments = [segment({ action: "remove", category: "bank_account", original: "1234-5", disclosed: "" })];
    render(
      <DisclosureInspector inspection={available(segments)} categories={[]} treatment="b1" strategy="b1" />,
    );
    await openInspector();

    await userEvent.click(screen.getByText("1234-5"));

    expect(screen.getByText(copy.disclosureInspector.detailReasonUnavailable)).toBeInTheDocument();
  });

  it("fails closed for an unrecognized action and unrecognized category", async () => {
    const segments = [segment({ action: "quantum_redact", category: "shoe_size", original: "42", disclosed: "??" })];
    render(
      <DisclosureInspector inspection={available(segments)} categories={[]} treatment="b3" strategy="b3" />,
    );
    await openInspector();

    await userEvent.click(screen.getByText("42"));

    const detailPanel = screen.getByTestId("inspector-detail-panel");
    expect(within(detailPanel).getByText(copy.inspectionActions.unknown.label)).toBeInTheDocument();
    expect(within(detailPanel).getByText(copy.categories.unrecognized)).toBeInTheDocument();
    expect(within(detailPanel).getByText("shoe_size")).toBeInTheDocument();
  });

  it("shows a hint instead of details before anything is selected", async () => {
    render(
      <DisclosureInspector
        inspection={available([segment({ original: "x", disclosed: "x" })])}
        categories={[]}
        treatment="b0"
        strategy="b0"
      />,
    );
    await openInspector();

    expect(screen.getByText(copy.disclosureInspector.noSelectionHint)).toBeInTheDocument();
  });
});

describe("DisclosureInspector -- unavailable states", () => {
  it("shows the blocked message and no columns when unavailable_reason is blocked", () => {
    render(
      <DisclosureInspector
        inspection={{ available: false, unavailable_reason: "blocked", segments: [] }}
        categories={[]}
        treatment="b4"
        strategy="b4"
      />,
    );

    expect(screen.getByText(copy.disclosureInspector.unavailableBlockedHeading)).toBeInTheDocument();
    expect(screen.queryByText(copy.disclosureInspector.originalColumnHeading)).not.toBeInTheDocument();
  });

  it("shows the alignment-failed message when unavailable_reason is alignment_failed", () => {
    render(
      <DisclosureInspector
        inspection={{ available: false, unavailable_reason: "alignment_failed", segments: [] }}
        categories={[]}
        treatment="b4"
        strategy="b4"
      />,
    );

    expect(screen.getByText(copy.disclosureInspector.unavailableAlignmentFailedHeading)).toBeInTheDocument();
  });
});
