import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { vi } from "vitest";

import { renderWithLocale } from "@/i18n/renderWithLocale";
import { copy } from "@/lib/copy";
import { en } from "@/lib/copy.en";

import { WelcomeScreen } from "./WelcomeScreen";

beforeEach(() => {
  window.localStorage.clear();
});

describe("WelcomeScreen", () => {
  it("renders the heading and CTA from copy.ts, not hardcoded text", () => {
    render(<WelcomeScreen onStart={vi.fn()} />);

    expect(screen.getByRole("heading", { level: 1, name: copy.howItWorks.title })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: copy.howItWorks.ctaPrimary })).toBeInTheDocument();
  });

  it("calls onStart when the primary CTA is clicked", async () => {
    const onStart = vi.fn();
    render(<WelcomeScreen onStart={onStart} />);

    await userEvent.click(screen.getByRole("button", { name: copy.howItWorks.ctaPrimary }));

    expect(onStart).toHaveBeenCalledTimes(1);
  });
});

/**
 * Issue #82 (T30): a first-time visitor must understand, from the welcome
 * screen alone, WHY the gateway exists before anything else -- not just
 * WHAT the three pipeline steps are named.
 */
describe("WelcomeScreen -- problem statement (T30)", () => {
  it("renders the plain-language problem statement before the primary CTA in reading order", () => {
    render(<WelcomeScreen onStart={vi.fn()} />);

    const heading = screen.getByRole("heading", { level: 1 });
    const problemHeading = screen.getByRole("heading", { name: copy.howItWorks.problem.heading });
    const cta = screen.getByRole("button", { name: copy.howItWorks.ctaPrimary });

    // DOM order: h1 -> problem statement -> ... -> primary CTA.
    expect(heading.compareDocumentPosition(problemHeading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(problemHeading.compareDocumentPosition(cta) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByText(copy.howItWorks.problem.statement)).toBeInTheDocument();
  });
});

/**
 * Issue #82 (T30): the trust boundary must be visually/structurally
 * obvious -- local steps grouped against external ones, with a labelled
 * boundary, never color alone. This is checked structurally (each step
 * carries its own group label as TEXT, not just a CSS class) so the test can
 * actually fail if a future edit drops the boundary group labelling instead
 * of merely reflowing CSS.
 */
describe("WelcomeScreen -- trust boundary diagram (T30)", () => {
  it("renders all six flow steps in the documented order", () => {
    render(<WelcomeScreen onStart={vi.fn()} />);

    const steps = copy.howItWorks.trustBoundary.steps;
    const orderedLabels = [
      steps.originalDocument,
      steps.localGateway,
      steps.disclosedRepresentation,
      steps.externalLlm,
      steps.response,
      steps.localReconstruction,
    ];

    const list = screen.getByRole("list", { name: copy.howItWorks.trustBoundary.heading });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(6);
    items.forEach((item, index) => {
      expect(item).toHaveTextContent(orderedLabels[index]);
    });
  });

  it("labels the local steps and the external steps with distinct, non-color text so the boundary never relies on color alone", () => {
    render(<WelcomeScreen onStart={vi.fn()} />);

    const list = screen.getByRole("list", { name: copy.howItWorks.trustBoundary.heading });
    const items = within(list).getAllByRole("listitem");

    // Documento original, Gateway local, Reconstrução local => local group.
    expect(items[0]).toHaveTextContent(copy.howItWorks.trustBoundary.localGroupLabel);
    expect(items[1]).toHaveTextContent(copy.howItWorks.trustBoundary.localGroupLabel);
    expect(items[5]).toHaveTextContent(copy.howItWorks.trustBoundary.localGroupLabel);

    // Representação divulgada, LLM externo, Resposta => external group.
    expect(items[2]).toHaveTextContent(copy.howItWorks.trustBoundary.externalGroupLabel);
    expect(items[3]).toHaveTextContent(copy.howItWorks.trustBoundary.externalGroupLabel);
    expect(items[4]).toHaveTextContent(copy.howItWorks.trustBoundary.externalGroupLabel);
  });

  it("provides a text alternative describing the diagram for assistive technology", () => {
    render(<WelcomeScreen onStart={vi.fn()} />);
    expect(screen.getByText(copy.howItWorks.trustBoundary.diagramAlt)).toBeInTheDocument();
  });
});

/**
 * Issue #82 (T30): PRESERVE/REMOVE/PSEUDONYMIZE/GENERALIZE explained with
 * tiny synthetic before->after examples, at the CONCEPT level -- no
 * vault/scope vocabulary here (that stays in technical details).
 */
describe("WelcomeScreen -- transformations explainer (T30)", () => {
  it("renders all four transformation kinds with a before/after example each", () => {
    render(<WelcomeScreen onStart={vi.fn()} />);

    const kinds = copy.howItWorks.transformations;
    for (const kind of [kinds.preserve, kinds.remove, kinds.pseudonymize, kinds.generalize]) {
      const card = screen.getByText(kind.label).closest("li") as HTMLElement;
      expect(card).not.toBeNull();
      expect(card.textContent).toContain(kind.before);
      expect(card.textContent).toContain(kind.after);
    }
  });

  it("never mentions vault/scope vocabulary at this concept level", () => {
    render(<WelcomeScreen onStart={vi.fn()} />);
    const text = document.body.textContent ?? "";
    expect(text.toLowerCase()).not.toContain("vault");
    expect(text.toLowerCase()).not.toContain("cofre");
  });
});

/**
 * Issue #82 (T30): the primary path (heading, problem, diagram,
 * transformations, primary CTA) must never force B0-B4 knowledge onto a
 * first-time visitor -- that vocabulary is confined to the secondary
 * "Como funciona a pesquisa?" disclosure, closed by default.
 */
describe("WelcomeScreen -- no B0-B4 vocabulary on the primary path (T30)", () => {
  it("renders no b0-b4 identifier before the research disclosure is opened", () => {
    render(<WelcomeScreen onStart={vi.fn()} />);
    const text = document.body.textContent?.toLowerCase() ?? "";
    for (const code of ["b0", "b1", "b2", "b3", "b4"]) {
      expect(text).not.toContain(code);
    }
  });

  it("reveals the treatment sequence, using semantic names, only after opening the research disclosure", async () => {
    render(<WelcomeScreen onStart={vi.fn()} />);

    const toggle = screen.getByText(copy.howItWorks.ctaSecondary);
    expect(screen.queryByText(copy.treatments.b0.name)).not.toBeInTheDocument();

    await userEvent.click(toggle);

    expect(screen.getByText(copy.treatments.b0.name)).toBeInTheDocument();
    expect(screen.getByText(copy.treatments.b4.name)).toBeInTheDocument();
    expect(screen.getByText(copy.howItWorks.researchDisclosure.noChoiceNeeded)).toBeInTheDocument();
  });
});

describe("WelcomeScreen -- switches to English (T21 fourth slice)", () => {
  it("renders the English heading, problem statement and CTA when en is the active locale", async () => {
    await renderWithLocale(<WelcomeScreen onStart={vi.fn()} />, "en");

    expect(screen.getByRole("heading", { level: 1, name: en.howItWorks.title })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: en.howItWorks.ctaPrimary })).toBeInTheDocument();
    expect(screen.getByText(en.howItWorks.problem.statement)).toBeInTheDocument();
    expect(screen.queryByText(copy.howItWorks.title)).not.toBeInTheDocument();
  });
});
