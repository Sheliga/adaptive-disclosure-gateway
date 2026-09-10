import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useReducer } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithLocale } from "@/i18n/renderWithLocale";
import type { ExampleSummary } from "@/lib/contracts";
import { copy } from "@/lib/copy";
import { enUS } from "@/lib/copy.en-US";
import { flowReducer, initialComposeState, type ComposeState, type FlowEvent } from "@/lib/flow";

import { ComposeScreen } from "./ComposeScreen";

beforeEach(() => {
  window.localStorage.clear();
});

const EXAMPLES: ExampleSummary[] = [
  {
    example_id: "ex-1",
    title: "Contrato de exemplo",
    domain: "legal",
    purpose: "demo",
    task: "Resuma o contrato.",
    character_count: 500,
  },
];

/** Wraps ComposeScreen with a real reducer so dispatched events actually update the UI. */
function Harness({
  onSubmit = vi.fn(),
  examples = EXAMPLES,
}: {
  onSubmit?: () => void;
  examples?: ExampleSummary[] | null;
}) {
  const [compose, dispatch] = useReducer(
    (state: ComposeState, event: FlowEvent) => {
      const next = flowReducer({ screen: "compose", compose: state, submitError: null }, event);
      return next.screen === "compose" ? next.compose : state;
    },
    initialComposeState,
  );

  return (
    <ComposeScreen
      compose={compose}
      submitError={null}
      examples={examples}
      examplesError={null}
      dispatch={dispatch}
      onSubmit={onSubmit}
    />
  );
}

describe("ComposeScreen -- no B0-B4 vocabulary, no treatment/strategy selector", () => {
  it("renders no b0-b4 identifiers anywhere in the visible text", () => {
    render(<Harness />);
    const text = document.body.textContent?.toLowerCase() ?? "";
    for (const code of ["b0", "b1", "b2", "b3", "b4"]) {
      expect(text).not.toContain(code);
    }
  });

  it("exposes no treatment/strategy/provider/policy selector control", () => {
    render(<Harness />);
    expect(screen.queryByLabelText(/estratégia|tratamento|provedor|política/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: /estratégia|tratamento|provedor/i })).not.toBeInTheDocument();
  });
});

describe("ComposeScreen -- entry modes and labels come from copy.ts", () => {
  it("renders the three entry mode options by their copy.ts labels", () => {
    render(<Harness />);
    expect(screen.getByRole("radio", { name: copy.entryModes.useExample })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: copy.entryModes.uploadFile })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: copy.entryModes.pasteText })).toBeInTheDocument();
  });

  it("shows the example select by default and disables submit until one is chosen", async () => {
    render(<Harness />);
    const submit = screen.getByRole("button", { name: copy.newTest.continueToReview });
    expect(submit).toBeDisabled();

    await userEvent.selectOptions(
      screen.getByLabelText(copy.newTest.exampleFieldLabel),
      "ex-1",
    );
    expect(submit).toBeEnabled();
  });

  it("switches to the paste textarea and enables submit once text is entered", async () => {
    render(<Harness />);
    await userEvent.click(screen.getByRole("radio", { name: copy.entryModes.pasteText }));

    const textarea = screen.getByLabelText(copy.newTest.pasteLabel);
    const submit = screen.getByRole("button", { name: copy.newTest.continueToReview });
    expect(submit).toBeDisabled();

    await userEvent.type(textarea, "algum conteúdo");
    expect(submit).toBeEnabled();
  });
});

describe("ComposeScreen -- file upload", () => {
  it("sends file_content + filename shaped data for a supported .txt file", async () => {
    render(<Harness />);
    await userEvent.click(screen.getByRole("radio", { name: copy.entryModes.uploadFile }));

    const input = screen.getByLabelText(copy.newTest.uploadFieldLabel) as HTMLInputElement;
    const file = new File(["conteudo do arquivo"], "notas.txt", { type: "text/plain" });
    await userEvent.upload(input, file);

    expect(await screen.findByText("notas.txt")).toBeInTheDocument();
    expect(screen.getByText("text/plain")).toBeInTheDocument();

    const submit = screen.getByRole("button", { name: copy.newTest.continueToReview });
    expect(submit).toBeEnabled();
  });

  it("accepts .md files too", async () => {
    render(<Harness />);
    await userEvent.click(screen.getByRole("radio", { name: copy.entryModes.uploadFile }));

    const input = screen.getByLabelText(copy.newTest.uploadFieldLabel) as HTMLInputElement;
    const file = new File(["# titulo"], "notas.md", { type: "text/markdown" });
    await userEvent.upload(input, file);

    expect(await screen.findByText("notas.md")).toBeInTheDocument();
  });

  it("refuses an unsupported extension client-side with copy.ts text, never reading it or enabling submit", async () => {
    render(<Harness />);
    await userEvent.click(screen.getByRole("radio", { name: copy.entryModes.uploadFile }));

    const file = new File(["%PDF-1.4 binary content"], "scan.pdf", { type: "application/pdf" });
    // Drag-and-drop (unlike userEvent.upload through a real file picker) is
    // not constrained by the input's `accept` attribute, so this is the
    // realistic path for an unsupported file actually reaching the app --
    // exactly why client-side validation in `readFile` matters here.
    fireEvent.drop(screen.getByText(copy.newTest.uploadDropHint).parentElement as HTMLElement, {
      dataTransfer: { files: [file] },
    });

    expect(await screen.findByText(copy.newTest.uploadUnsupportedType)).toBeInTheDocument();
    expect(screen.queryByText("scan.pdf")).not.toBeInTheDocument();

    const submit = screen.getByRole("button", { name: copy.newTest.continueToReview });
    expect(submit).toBeDisabled();
  });
});

describe("ComposeScreen -- submit", () => {
  it("calls onSubmit only when the form is actually submitted with a ready compose state", async () => {
    const onSubmit = vi.fn();
    render(<Harness onSubmit={onSubmit} />);

    await userEvent.selectOptions(screen.getByLabelText(copy.newTest.exampleFieldLabel), "ex-1");
    await userEvent.click(screen.getByRole("button", { name: copy.newTest.continueToReview }));

    expect(onSubmit).toHaveBeenCalledTimes(1);
  });
});

describe("ComposeScreen -- switches to English (T21 fourth slice)", () => {
  it("renders English entry-mode/field labels when en-US is the active locale", async () => {
    await renderWithLocale(<Harness />, "en-US");

    expect(screen.getByRole("heading", { name: enUS.newTest.heading })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: enUS.entryModes.useExample })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: enUS.entryModes.uploadFile })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: enUS.entryModes.pasteText })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: enUS.newTest.continueToReview })).toBeInTheDocument();
    expect(screen.queryByText(copy.newTest.heading)).not.toBeInTheDocument();
  });
});
