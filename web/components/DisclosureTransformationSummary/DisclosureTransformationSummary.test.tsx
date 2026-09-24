import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { renderWithLocale } from "@/i18n/renderWithLocale";
import type { DisclosureInspection, InspectionSegment } from "@/lib/contracts";
import { copy } from "@/lib/copy";
import { en } from "@/lib/copy.en";

import { DisclosureTransformationSummary } from "./DisclosureTransformationSummary";

beforeEach(() => {
  window.localStorage.clear();
});

function seg(
  original: string,
  disclosed: string,
  action: string | null = null,
  category: string | null = null,
): InspectionSegment {
  return { original, disclosed, action, category };
}

function available(segments: InspectionSegment[]): DisclosureInspection {
  return { available: true, unavailable_reason: null, segments };
}

/**
 * The canonical fixture the issue asks for: plain text, a pseudonymized
 * name, a generalized salary, a removed CPF, plain text -- in exactly the
 * order the backend (T27 / `application/inspection.py`) emits them.
 */
const SEGMENTS: InspectionSegment[] = [
  seg("Relatório de ", "Relatório de "),
  seg("Maria Silva", "PESSOA_7f3a", "pseudonymize", "employee_name"),
  seg(", salário ", ", salário "),
  seg("R$ 8.500,00", "R$ 5.000-10.000", "generalize", "salary"),
  seg(", CPF ", ", CPF "),
  seg("123.456.789-00", "", "remove", "cpf"),
  seg(" fim.", " fim."),
];

function segmentTexts(column: HTMLElement): string[] {
  return Array.from(column.querySelectorAll("[data-segment-text]")).map((node) => node.textContent ?? "");
}

function original(): HTMLElement {
  return screen.getByTestId("before-after-original");
}

function disclosed(): HTMLElement {
  return screen.getByTestId("before-after-disclosed");
}

/** Raw identifiers that must never be the primary label, nor leak at all here. */
const TECHNICAL_IDS = [
  /\bemployee_name\b/,
  /\bsalary\b/,
  /\bcpf\b/,
  /\bpseudonymize\b/,
  /\bgeneralize\b/,
  /\bremove\b/,
  /\bb[0-4]\b/,
  /\brecommended\b/,
  /\bhr-v\d\b/,
];

describe("DisclosureTransformationSummary -- available inspection (T32.3 / #103)", () => {
  it("renders original and disclosed segments in the exact backend order, with no interaction", () => {
    render(<DisclosureTransformationSummary inspection={available(SEGMENTS)} variant="review" />);

    expect(segmentTexts(original())).toEqual(SEGMENTS.map((s) => s.original));
    expect(segmentTexts(disclosed())).toEqual([
      "Relatório de ",
      "PESSOA_7f3a",
      ", salário ",
      "R$ 5.000-10.000",
      ", CPF ",
      copy.inspectionActions.removedMarker,
      " fim.",
    ]);
  });

  it("marks a removed segment explicitly on the disclosed side instead of rendering its empty value", () => {
    render(<DisclosureTransformationSummary inspection={available(SEGMENTS)} variant="review" />);

    const removed = disclosed().querySelectorAll('[data-action="remove"]');
    expect(removed).toHaveLength(1);
    expect(removed[0].querySelector("[data-segment-text]")?.textContent).toBe(copy.inspectionActions.removedMarker);
    // The original CPF never appears on the disclosed side.
    expect(disclosed().textContent).not.toContain("123.456.789-00");
  });

  it("labels every transformed passage with human text: category on the original side, action on the sent side", () => {
    render(<DisclosureTransformationSummary inspection={available(SEGMENTS)} variant="review" />);

    const originalMarks = Array.from(original().querySelectorAll("[data-action]"));
    expect(originalMarks.map((mark) => mark.textContent)).toEqual([
      expect.stringContaining(copy.categories.labels.employee_name),
      expect.stringContaining(copy.categories.labels.salary),
      expect.stringContaining(copy.categories.labels.cpf),
    ]);
    const disclosedMarks = Array.from(disclosed().querySelectorAll("[data-action]"));
    expect(disclosedMarks[0].textContent).toContain(copy.inspectionActions.pseudonymize.label);
    expect(disclosedMarks[1].textContent).toContain(copy.inspectionActions.generalize.label);
    expect(disclosedMarks[2].textContent).toContain(copy.inspectionActions.removedMarker);
  });

  it("states the disclosed side as prepared/reviewed, never a byte-identity promise with a later execute call", () => {
    render(<DisclosureTransformationSummary inspection={available(SEGMENTS)} variant="review" />);

    expect(screen.getByRole("heading", { name: copy.beforeAfter.heading })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: copy.beforeAfter.originalHeading })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: copy.beforeAfter.disclosedHeadingReview })).toBeInTheDocument();
    expect(screen.getByText(copy.beforeAfter.transformationStep)).toBeInTheDocument();
    expect(screen.getByText(copy.beforeAfter.disclosedCaptionReview)).toBeInTheDocument();

    // #103 review fix (PR #108): the Review caption states what the gateway
    // PREPARED for this review, not a promise that it is exactly what
    // crosses the boundary later at execute time -- structurally true only
    // for upload, not for paste/example (see DisclosureTransformationSummary's
    // docstring). A regression back to the old identity-claim wording must
    // fail this test.
    expect(copy.beforeAfter.disclosedCaptionReview).toMatch(/preparou/);
    expect(copy.beforeAfter.disclosedCaptionReview).toMatch(/revis(ã|a)o/);
    expect(document.body.textContent).not.toMatch(/Exatamente esta representação/);
    expect(document.body.textContent).not.toMatch(/cruza a fronteira.*confirmar/);
  });

  it("reads Original -> local transformation -> sent, in DOM order", () => {
    render(<DisclosureTransformationSummary inspection={available(SEGMENTS)} variant="review" />);

    const step = screen.getByText(copy.beforeAfter.transformationStep);
    expect(original().compareDocumentPosition(step) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(step.compareDocumentPosition(disclosed()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("counts transformations by segment.action !== null, never by category occurrence counts", () => {
    render(<DisclosureTransformationSummary inspection={available(SEGMENTS)} variant="review" />);

    expect(screen.getByText(copy.beforeAfter.handledCount.replace("{n}", "3"))).toBeInTheDocument();
  });

  it("shows no technical identifier, treatment, strategy, reason or ordinal", () => {
    const { container } = render(
      <DisclosureTransformationSummary inspection={available(SEGMENTS)} variant="review" />,
    );

    const text = container.textContent ?? "";
    for (const pattern of TECHNICAL_IDS) {
      expect(text).not.toMatch(pattern);
    }
    expect(text).not.toContain(copy.disclosureInspector.detailReasonLabel);
    expect(text).not.toMatch(/Item \d+ de \d+/);
  });

  it("makes no segment individually focusable or interactive", () => {
    const { container } = render(
      <DisclosureTransformationSummary inspection={available(SEGMENTS)} variant="review" />,
    );

    expect(container.querySelectorAll("button, a, input, [tabindex]")).toHaveLength(0);
  });

  it("preserves whitespace and Unicode verbatim, including line breaks", () => {
    const segments = [
      seg("Olá 👋 José\n", "Olá 👋 José\n"),
      seg("Ana Luíza Ñandú", "PESSOA_β", "pseudonymize", "employee_name"),
      seg("\n  recuo", "\n  recuo"),
    ];
    render(<DisclosureTransformationSummary inspection={available(segments)} variant="review" />);

    expect(segmentTexts(original()).join("")).toBe("Olá 👋 José\nAna Luíza Ñandú\n  recuo");
    expect(segmentTexts(disclosed()).join("")).toBe("Olá 👋 José\nPESSOA_β\n  recuo");
  });

  it("says nothing was changed when no segment carries an action", () => {
    render(
      <DisclosureTransformationSummary inspection={available([seg("texto neutro", "texto neutro")])} variant="review" />,
    );

    expect(screen.getByText(copy.beforeAfter.noChanges)).toBeInTheDocument();
    expect(disclosed().querySelectorAll("[data-action]")).toHaveLength(0);
  });

  it("uses the approved wording in the approved variant", () => {
    render(<DisclosureTransformationSummary inspection={available(SEGMENTS)} variant="approved" />);

    expect(screen.getByRole("heading", { name: copy.beforeAfter.disclosedHeadingApproved })).toBeInTheDocument();
    expect(screen.getByText(copy.beforeAfter.disclosedCaptionApproved)).toBeInTheDocument();
    expect(screen.queryByText(copy.beforeAfter.disclosedHeadingReview)).not.toBeInTheDocument();
    // #103 review fix (PR #108): the Approved caption is historical/read-only
    // ("apresentada para sua aprovação"), never a claim that this is exactly
    // what was later sent.
    expect(document.body.textContent).not.toMatch(/Exatamente esta representação/);
  });

  it("can omit its own heading when embedded under another one", () => {
    render(<DisclosureTransformationSummary inspection={available(SEGMENTS)} variant="approved" showHeading={false} />);

    expect(screen.queryByRole("heading", { name: copy.beforeAfter.heading })).not.toBeInTheDocument();
    expect(segmentTexts(original())).toEqual(SEGMENTS.map((s) => s.original));
  });

  it("renders in English under the en locale", async () => {
    await renderWithLocale(<DisclosureTransformationSummary inspection={available(SEGMENTS)} variant="review" />, "en");

    expect(screen.getByRole("heading", { name: en.beforeAfter.heading })).toBeInTheDocument();
    expect(screen.getByText(en.beforeAfter.transformationStep)).toBeInTheDocument();
    expect(within(disclosed()).getByText(en.inspectionActions.removedMarker)).toBeInTheDocument();
    expect(original().textContent).toContain(en.categories.labels.employee_name);

    // #103 review fix (PR #108): same identity-claim guard, English locale.
    expect(en.beforeAfter.disclosedCaptionReview).toMatch(/prepared/);
    expect(en.beforeAfter.disclosedCaptionReview).toMatch(/review/);
    expect(document.body.textContent).not.toMatch(/Exactly this representation/);
    expect(document.body.textContent).not.toMatch(/crosses the boundary.*confirm/);
  });
});

describe("DisclosureTransformationSummary -- fail-closed labels", () => {
  it("renders an unknown action with the unrecognized label, never the raw action id", () => {
    render(
      <DisclosureTransformationSummary
        inspection={available([seg("Maria", "M***", "tokenize_v9", "employee_name")])}
        variant="review"
      />,
    );

    const mark = disclosed().querySelector("[data-action]");
    expect(mark?.getAttribute("data-action")).toBe("unknown");
    expect(mark?.textContent).toContain(copy.inspectionActions.unknown.label);
    expect(document.body.textContent).not.toContain("tokenize_v9");
    // Never presented as one of the four known actions.
    for (const known of ["preserve", "pseudonymize", "generalize", "remove"] as const) {
      expect(mark?.textContent).not.toContain(copy.inspectionActions[known].label);
    }
  });

  it("renders an unknown category with the unrecognized label, never the raw category id", () => {
    render(
      <DisclosureTransformationSummary
        inspection={available([seg("AB123456", "[doc]", "generalize", "passport_number")])}
        variant="review"
      />,
    );

    const mark = original().querySelector("[data-action]");
    expect(mark?.textContent).toContain(copy.categories.unrecognized);
    expect(document.body.textContent).not.toContain("passport_number");
  });
});

describe("DisclosureTransformationSummary -- unavailable inspection never fabricates a before/after", () => {
  function unavailable(reason: string): DisclosureInspection {
    return { available: false, unavailable_reason: reason, segments: [] };
  }

  it.each([
    ["blocked", copy.beforeAfter.unavailableBlocked],
    ["alignment_failed", copy.beforeAfter.unavailableAlignmentFailed],
    ["some_future_reason", copy.beforeAfter.unavailableUnknown],
  ])("reason %s renders only its plain message, with no columns and no sent heading", (reason, message) => {
    render(<DisclosureTransformationSummary inspection={unavailable(reason)} variant="review" />);

    expect(screen.getByText(message)).toBeInTheDocument();
    expect(screen.queryByTestId("before-after-original")).not.toBeInTheDocument();
    expect(screen.queryByTestId("before-after-disclosed")).not.toBeInTheDocument();
    expect(screen.queryByText(copy.beforeAfter.disclosedHeadingReview)).not.toBeInTheDocument();
    expect(screen.queryByText(copy.beforeAfter.handledCount.replace("{n}", "0"))).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain(reason);
  });
});
