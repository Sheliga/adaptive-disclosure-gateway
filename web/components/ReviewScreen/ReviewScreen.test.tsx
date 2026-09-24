import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithLocale } from "@/i18n/renderWithLocale";
import type {
  CategoryDisclosureSummary,
  DisclosureInspection,
  ExampleSummary,
  PreviewResponse,
} from "@/lib/contracts";
import { copy } from "@/lib/copy";
import { en } from "@/lib/copy.en";
import { initialComposeState, type ComposeState } from "@/lib/flow";

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

function preview(
  categories: CategoryDisclosureSummary[],
  status: "allowed" | "blocked" = "allowed",
  inspection: DisclosureInspection | null = null,
  vaultExplorerToken: string | null = null,
): PreviewResponse {
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
    inspection,
    vault_explorer_token: vaultExplorerToken,
  };
}

/**
 * T30 / issue #82: the review hierarchy must read, in DOM order, "what was
 * detected" -> "what stays local" -> "exactly what will be sent" -> confirm
 * -- the decision the reviewer is being asked to make. This can fail from a
 * real defect: reordering sections, or losing the prominent "will be sent"
 * heading, breaks it.
 */
describe("ReviewScreen -- hierarchy order (T30)", () => {
  it("orders detected -> stays local -> will be sent -> confirm in the DOM", () => {
    render(
      <ReviewScreen
        preview={preview([category({ category: "cpf", crosses_trust_boundary: false })])}
        executeError={null}
        onConfirm={vi.fn()}
        onEdit={vi.fn()}
      />,
    );

    const detected = screen.getByText(copy.sectionHeadings.whatWasDetected);
    const stayLocal = screen.getByText(copy.sectionHeadings.whatStaysLocal);
    const willBeSent = screen.getByText(copy.review.willBeSentHeading);
    const confirm = screen.getByRole("button", { name: copy.review.confirmSend });

    const positions = [detected, stayLocal, willBeSent, confirm];
    for (let i = 0; i < positions.length - 1; i += 1) {
      expect(
        positions[i].compareDocumentPosition(positions[i + 1]) & Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
    }
  });

  it("renders the prominent, unambiguously labelled 'will be sent' heading", () => {
    render(
      <ReviewScreen preview={preview([category({})])} executeError={null} onConfirm={vi.fn()} onEdit={vi.fn()} />,
    );
    expect(screen.getByRole("heading", { name: copy.review.willBeSentHeading })).toBeInTheDocument();
  });

  it("never renders a b0-b4 identifier in the level-1 region before any technical disclosure is opened", () => {
    render(
      <ReviewScreen preview={preview([category({})])} executeError={null} onConfirm={vi.fn()} onEdit={vi.fn()} />,
    );
    const text = document.body.textContent?.toLowerCase() ?? "";
    for (const code of ["b0", "b1", "b2", "b3", "b4"]) {
      expect(text).not.toContain(code);
    }
  });
});

describe("ReviewScreen -- local vs sent split follows crosses_trust_boundary", () => {
  it("groups a removed category with crosses_trust_boundary=false under 'what stays local'", () => {
    render(
      <ReviewScreen
        preview={preview([category({ category: "cpf", outcome: "removed", crosses_trust_boundary: false })])}
        executeError={null}
        onConfirm={vi.fn()}
        onEdit={vi.fn()}
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
        onEdit={vi.fn()}
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
        onEdit={vi.fn()}
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
        onEdit={vi.fn()}
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
    render(<ReviewScreen preview={p} executeError={null} onConfirm={vi.fn()} onEdit={vi.fn()} />);
    expect(screen.queryByText(p.external_payload)).not.toBeInTheDocument();
  });

  it("appears only after the disclosure control is opened", async () => {
    const p = preview([category({})]);
    render(<ReviewScreen preview={p} executeError={null} onConfirm={vi.fn()} onEdit={vi.fn()} />);

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
        onEdit={vi.fn()}
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
        onEdit={vi.fn()}
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
      <ReviewScreen preview={preview([category({})])} executeError={null} onConfirm={onConfirm} onEdit={vi.fn()} />,
    );
    await userEvent.click(screen.getByRole("button", { name: copy.review.confirmSend }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("calls onEdit (and never onConfirm) when the Change action is clicked", async () => {
    const onEdit = vi.fn();
    const onConfirm = vi.fn();
    render(
      <ReviewScreen preview={preview([category({})])} executeError={null} onConfirm={onConfirm} onEdit={onEdit} />,
    );
    await userEvent.click(screen.getByRole("button", { name: copy.review.changeRequest }));
    expect(onEdit).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("renders a retry-visible execute error without hiding the confirm action", () => {
    render(
      <ReviewScreen
        preview={preview([category({})])}
        executeError={{ message: "falha ao enviar", kind: null, fields: null }}
        onConfirm={vi.fn()}
        onEdit={vi.fn()}
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
        onEdit={vi.fn()}
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
        onEdit={vi.fn()}
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
        onEdit={vi.fn()}
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
        onEdit={vi.fn()}
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
        onEdit={vi.fn()}
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
      <ReviewScreen preview={p} executeError={null} onConfirm={vi.fn()} onEdit={vi.fn()} />,
      "en",
    );

    await userEvent.click(screen.getByText(en.review.showPayloadToggle));

    expect(await screen.findByText(p.external_payload)).toBeInTheDocument();
  });
});

/**
 * T27 / issue #69: `ReviewScreen` renders the transformation inspector only
 * when `preview.inspection !== null`, and only via the inspector's own
 * collapsed disclosure -- its content must stay out of the DOM here too,
 * for the same reason `external_payload` does.
 */
describe("ReviewScreen -- disclosure inspector (T27), now behind a Level-2 disclosure (T30)", () => {
  it("renders no Level-2 disclosure at all when inspection is null", () => {
    render(
      <ReviewScreen preview={preview([category({})])} executeError={null} onConfirm={vi.fn()} onEdit={vi.fn()} />,
    );

    expect(screen.queryByText(copy.review.understandChangesToggle)).not.toBeInTheDocument();
    expect(screen.queryByText(copy.disclosureInspector.toggleLabel)).not.toBeInTheDocument();
  });

  it("keeps the inspector's own toggle out of the DOM until the Level-2 disclosure is opened", async () => {
    const inspection = {
      available: true,
      unavailable_reason: null,
      segments: [{ action: null, category: null, original: "hello", disclosed: "hello" }],
    };
    render(
      <ReviewScreen
        preview={preview([category({})], "allowed", inspection)}
        demoInspectionEnabled
        executeError={null}
        onConfirm={vi.fn()}
        onEdit={vi.fn()}
      />,
    );

    expect(screen.getByText(copy.review.understandChangesToggle)).toBeInTheDocument();
    expect(screen.queryByText(copy.disclosureInspector.toggleLabel)).not.toBeInTheDocument();

    await userEvent.click(screen.getByText(copy.review.understandChangesToggle));

    expect(screen.getByText(copy.disclosureInspector.toggleLabel)).toBeInTheDocument();
    // Scoped to the Level-2 disclosure: the T32.3 before/after above it has
    // its own "Original" heading.
    const levelTwo = screen.getByText(copy.review.understandChangesToggle).closest("details") as HTMLElement;
    expect(within(levelTwo).queryByText(copy.disclosureInspector.originalColumnHeading)).not.toBeInTheDocument();

    await userEvent.click(screen.getByText(copy.disclosureInspector.toggleLabel));

    expect(within(levelTwo).getByText(copy.disclosureInspector.originalColumnHeading)).toBeInTheDocument();
  });

  it("renders the unavailable message once the Level-2 disclosure is opened, when inspection.available is false", async () => {
    const inspection = { available: false as const, unavailable_reason: "blocked" as const, segments: [] };
    render(
      <ReviewScreen
        preview={preview([category({})], "allowed", inspection)}
        demoInspectionEnabled
        executeError={null}
        onConfirm={vi.fn()}
        onEdit={vi.fn()}
      />,
    );

    await userEvent.click(screen.getByText(copy.review.understandChangesToggle));

    expect(screen.getByText(copy.disclosureInspector.unavailableBlockedHeading)).toBeInTheDocument();
  });
});

/**
 * T28 / issue #70: `ExportRestorePanel` renders only when the caller passes
 * `demoTransparencyEnabled` AND the preview is allowed. `demoTransparencyEnabled`
 * defaults to `false`, so every existing render call in this file (which
 * never passes it) already proves the "disabled" half of this pin.
 */
describe("ReviewScreen -- export/restore panel (T28), now behind a Level-3 disclosure (T30)", () => {
  it("does not render the panel or the Level-3 disclosure when demoTransparencyEnabled is not passed (defaults to disabled)", () => {
    render(
      <ReviewScreen preview={preview([category({})])} executeError={null} onConfirm={vi.fn()} onEdit={vi.fn()} />,
    );

    expect(screen.queryByText(copy.review.technicalToolsToggle)).not.toBeInTheDocument();
    expect(screen.queryByText(copy.exportRestorePanel.heading)).not.toBeInTheDocument();
  });

  it("does not render the panel when explicitly disabled", () => {
    render(
      <ReviewScreen
        preview={preview([category({})])}
        executeError={null}
        onConfirm={vi.fn()}
        onEdit={vi.fn()}
        demoTransparencyEnabled={false}
      />,
    );

    expect(screen.queryByText(copy.review.technicalToolsToggle)).not.toBeInTheDocument();
    expect(screen.queryByText(copy.exportRestorePanel.heading)).not.toBeInTheDocument();
  });

  it("renders the Level-3 disclosure, collapsed, then the panel once opened, when enabled and the preview is allowed", async () => {
    render(
      <ReviewScreen
        preview={preview([category({})], "allowed")}
        executeError={null}
        onConfirm={vi.fn()}
        onEdit={vi.fn()}
        demoTransparencyEnabled={true}
      />,
    );

    expect(screen.getByText(copy.review.technicalToolsToggle)).toBeInTheDocument();
    expect(screen.queryByText(copy.exportRestorePanel.heading)).not.toBeInTheDocument();

    await userEvent.click(screen.getByText(copy.review.technicalToolsToggle));

    expect(screen.getByText(copy.exportRestorePanel.heading)).toBeInTheDocument();
  });

  it("does not render the panel when enabled but the preview is blocked", () => {
    render(
      <ReviewScreen
        preview={preview([category({ outcome: "blocked" })], "blocked")}
        executeError={null}
        onConfirm={vi.fn()}
        onEdit={vi.fn()}
        demoTransparencyEnabled={true}
      />,
    );

    expect(screen.queryByText(copy.review.technicalToolsToggle)).not.toBeInTheDocument();
    expect(screen.queryByText(copy.exportRestorePanel.heading)).not.toBeInTheDocument();
  });
});

/**
 * T29 / issue #72: `VaultExplorerPanel` renders whenever the caller passes
 * `demoVaultExplorerEnabled={true}`, regardless of `preview.summary.status`
 * -- unlike the export/restore panel above, a blocked decision's `null`
 * token is a legitimate state the panel itself renders as "unavailable",
 * not a reason for this screen to hide the panel outright. Defaults to
 * `false`, so every existing render call in this file already proves the
 * "disabled" half of this pin.
 */
describe("ReviewScreen -- Vault Explorer panel (T29), now behind a Level-3 disclosure (T30)", () => {
  it("does not render the panel or the Level-3 disclosure when demoVaultExplorerEnabled is not passed (defaults to disabled), and makes no fetch call", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    render(
      <ReviewScreen
        preview={preview([category({})], "allowed", null, "vx1.token")}
        executeError={null}
        onConfirm={vi.fn()}
        onEdit={vi.fn()}
      />,
    );

    expect(screen.queryByText(copy.review.technicalToolsToggle)).not.toBeInTheDocument();
    expect(screen.queryByText(copy.vaultExplorerPanel.heading)).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("does not render the panel when explicitly disabled even though a token is present", () => {
    render(
      <ReviewScreen
        preview={preview([category({})], "allowed", null, "vx1.token")}
        executeError={null}
        onConfirm={vi.fn()}
        onEdit={vi.fn()}
        demoVaultExplorerEnabled={false}
      />,
    );

    expect(screen.queryByText(copy.review.technicalToolsToggle)).not.toBeInTheDocument();
    expect(screen.queryByText(copy.vaultExplorerPanel.heading)).not.toBeInTheDocument();
  });

  it("renders the panel with its unavailable note, once the Level-3 disclosure is opened, when enabled but the token is null", async () => {
    render(
      <ReviewScreen
        preview={preview([category({})], "allowed", null, null)}
        executeError={null}
        onConfirm={vi.fn()}
        onEdit={vi.fn()}
        demoVaultExplorerEnabled={true}
      />,
    );

    await userEvent.click(screen.getByText(copy.review.technicalToolsToggle));

    expect(screen.getByText(copy.vaultExplorerPanel.heading)).toBeInTheDocument();
    expect(screen.getByText(copy.vaultExplorerPanel.unavailableForDecision)).toBeInTheDocument();
  });

  it("renders the interactive panel when enabled and the token is non-null, still collapsed by its own toggle after the Level-3 disclosure is opened", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    render(
      <ReviewScreen
        preview={preview([category({})], "allowed", null, "vx1.token")}
        executeError={null}
        onConfirm={vi.fn()}
        onEdit={vi.fn()}
        demoVaultExplorerEnabled={true}
      />,
    );

    expect(screen.queryByText(copy.vaultExplorerPanel.heading)).not.toBeInTheDocument();

    await userEvent.click(screen.getByText(copy.review.technicalToolsToggle));

    expect(screen.getByText(copy.vaultExplorerPanel.heading)).toBeInTheDocument();
    expect(screen.getByText(copy.vaultExplorerPanel.toggleLabel)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});

/**
 * T32.2 / #102: Review must answer "what am I about to send/process?"
 * without the reviewer having to remember Compose. The context is built from
 * the retained ComposeState plus the examples catalog, and every value that
 * has no human copy fails closed to a neutral label rather than an invented
 * one or a raw identifier as the primary information.
 */
const EXAMPLES: ExampleSummary[] = [
  {
    example_id: "hr_team_summary_001",
    title: "hr_team_summary_001",
    domain: "hr",
    purpose: "team_summary",
    task: "Resuma a equipe sugerida pelo exemplo.",
    character_count: 400,
  },
];

function uploadCompose(overrides: Partial<ComposeState> = {}): ComposeState {
  const file = new File(["CONTEUDO-SECRETO-DO-ARQUIVO"], "contrato-sintetico.pdf", { type: "application/pdf" });
  return {
    ...initialComposeState,
    mode: "upload",
    file: { file, filename: file.name, byteSize: file.size, displayType: "Documento PDF" },
    documentType: "contract",
    analysisMode: "contract_summary",
    task: "Quais são os prazos?",
    ...overrides,
  };
}

function contextRegion() {
  return screen.getByRole("region", { name: copy.review.contextHeading });
}

describe("ReviewScreen -- 'What you asked for' context (#102)", () => {
  it("example mode: shows the source, the human example label and the task -- not the raw id as primary", () => {
    render(
      <ReviewScreen
        preview={preview([category({})])}
        executeError={null}
        onConfirm={vi.fn()}
        onEdit={vi.fn()}
        compose={{ ...initialComposeState, mode: "example", exampleId: "hr_team_summary_001", task: "Liste os cargos" }}
        examples={EXAMPLES}
      />,
    );
    const region = contextRegion();
    expect(region).toHaveTextContent(copy.review.sourceExample);
    const exampleValue = screen.getByText(copy.examplePurposes.team_summary);
    expect(region).toContainElement(exampleValue);
    expect(exampleValue.textContent).not.toContain("hr_team_summary_001");
    expect(region).toHaveTextContent("Liste os cargos");
  });

  it("example mode with a blank task: shows the example's suggested task, marked as suggested", () => {
    render(
      <ReviewScreen
        preview={preview([category({})])}
        executeError={null}
        onConfirm={vi.fn()}
        onEdit={vi.fn()}
        compose={{ ...initialComposeState, mode: "example", exampleId: "hr_team_summary_001", task: "  " }}
        examples={EXAMPLES}
      />,
    );
    const region = contextRegion();
    expect(region).toHaveTextContent(EXAMPLES[0].task);
    expect(region).toHaveTextContent(copy.review.exampleSuggestedTask);
  });

  it("example mode: an example missing from the catalog fails closed to the neutral label", () => {
    render(
      <ReviewScreen
        preview={preview([category({})])}
        executeError={null}
        onConfirm={vi.fn()}
        onEdit={vi.fn()}
        compose={{ ...initialComposeState, mode: "example", exampleId: "zz_unknown_042", task: "" }}
        examples={EXAMPLES}
      />,
    );
    const region = contextRegion();
    expect(screen.getAllByText(copy.review.unknownValue).length).toBeGreaterThan(0);
    expect(region).not.toHaveTextContent(copy.examplePurposes.team_summary);
    expect(region).not.toHaveTextContent(EXAMPLES[0].task);
  });

  it("upload mode: shows file name, human document type, human analysis type and task, never file content", () => {
    render(
      <ReviewScreen
        preview={preview([category({})])}
        executeError={null}
        onConfirm={vi.fn()}
        onEdit={vi.fn()}
        compose={uploadCompose()}
      />,
    );
    const region = contextRegion();
    expect(region).toHaveTextContent(copy.review.sourceUpload);
    expect(region).toHaveTextContent("contrato-sintetico.pdf");
    expect(region).toHaveTextContent(copy.newTest.documentTypeLabels.contract);
    expect(region).toHaveTextContent(copy.newTest.analysisModeLabels.contract_summary);
    expect(region).toHaveTextContent("Quais são os prazos?");
    expect(region).not.toHaveTextContent("contract_summary");
    expect(document.body.textContent).not.toContain("CONTEUDO-SECRETO-DO-ARQUIVO");
  });

  it("upload mode: unknown document/analysis types fail closed -- no raw id, no invented meaning", () => {
    render(
      <ReviewScreen
        preview={preview([category({})])}
        executeError={null}
        onConfirm={vi.fn()}
        onEdit={vi.fn()}
        compose={uploadCompose({ documentType: "mystery_doc", analysisMode: "mystery_mode" })}
      />,
    );
    const region = contextRegion();
    expect(region).not.toHaveTextContent("mystery_doc");
    expect(region).not.toHaveTextContent("mystery_mode");
    expect(screen.getAllByText(copy.review.unknownValue)).toHaveLength(2);
  });

  it("paste mode: says the source is pasted text and shows the task, without repeating the pasted text", () => {
    render(
      <ReviewScreen
        preview={preview([category({})])}
        executeError={null}
        onConfirm={vi.fn()}
        onEdit={vi.fn()}
        compose={{
          ...initialComposeState,
          mode: "paste",
          pastedText: "Texto colado com CPF 123.456.789-00",
          task: "Resuma os riscos",
        }}
      />,
    );
    const region = contextRegion();
    expect(region).toHaveTextContent(copy.review.sourcePaste);
    expect(region).toHaveTextContent("Resuma os riscos");
    expect(document.body.textContent).not.toContain("123.456.789-00");
  });

  it("paste mode with no task says so plainly instead of rendering an empty value", () => {
    render(
      <ReviewScreen
        preview={preview([category({})])}
        executeError={null}
        onConfirm={vi.fn()}
        onEdit={vi.fn()}
        compose={{ ...initialComposeState, mode: "paste", pastedText: "algo", task: "" }}
      />,
    );
    expect(contextRegion()).toHaveTextContent(copy.review.noTaskProvided);
  });

  it("orders heading -> context + Change -> detected -> local -> sent -> consequence -> confirm", () => {
    render(
      <ReviewScreen
        preview={preview([category({})])}
        executeError={null}
        onConfirm={vi.fn()}
        onEdit={vi.fn()}
        compose={{ ...initialComposeState, mode: "paste", pastedText: "algo", task: "t" }}
      />,
    );
    const order = [
      screen.getByRole("heading", { name: copy.review.heading }),
      screen.getByRole("heading", { name: copy.review.contextHeading }),
      screen.getByRole("button", { name: copy.review.changeRequest }),
      screen.getByText(copy.sectionHeadings.whatWasDetected),
      screen.getByText(copy.sectionHeadings.whatStaysLocal),
      screen.getByText(copy.review.willBeSentHeading),
      screen.getByText(copy.review.confirmConsequence),
      screen.getByRole("button", { name: copy.review.confirmSend }),
    ];
    for (let i = 0; i < order.length - 1; i += 1) {
      expect(order[i].compareDocumentPosition(order[i + 1]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    }
  });
});

describe("ReviewScreen -- irreversible boundary next to the CTA (#102)", () => {
  it("states that confirming starts the external call and that going back afterwards does not undo it", () => {
    render(
      <ReviewScreen preview={preview([category({})])} executeError={null} onConfirm={vi.fn()} onEdit={vi.fn()} />,
    );
    expect(screen.getByText(copy.review.confirmConsequence)).toBeInTheDocument();
    expect(screen.getByText(copy.review.afterSendNotice)).toBeInTheDocument();
    for (const text of [copy.review.confirmConsequence, copy.review.afterSendNotice]) {
      expect(text.toLowerCase()).not.toMatch(/\bb[0-4]\b/);
    }
  });

  it("a blocked preview has no CTA and therefore no send-consequence copy either", () => {
    render(
      <ReviewScreen preview={preview([], "blocked")} executeError={null} onConfirm={vi.fn()} onEdit={vi.fn()} />,
    );
    expect(screen.queryByText(copy.review.confirmConsequence)).not.toBeInTheDocument();
    // Editing is still offered: nothing was sent.
    expect(screen.getByRole("button", { name: copy.review.changeRequest })).toBeInTheDocument();
  });

  it("an execute error says nothing is retried automatically, and a new attempt needs an explicit confirm", () => {
    const onConfirm = vi.fn();
    render(
      <ReviewScreen
        preview={preview([category({})])}
        executeError={{ message: copy.errors.generic, kind: null, fields: null }}
        onConfirm={onConfirm}
        onEdit={vi.fn()}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(copy.errors.generic);
    expect(screen.getByText(copy.review.executeErrorNoAutoRetry)).toBeInTheDocument();
    expect(onConfirm).not.toHaveBeenCalled();
  });
});

describe("ReviewScreen -- context and boundary copy in English (#102)", () => {
  it("renders the context heading, Change action and boundary copy from the en table", async () => {
    await renderWithLocale(
      <ReviewScreen
        preview={preview([category({})])}
        executeError={null}
        onConfirm={vi.fn()}
        onEdit={vi.fn()}
        compose={uploadCompose()}
      />,
      "en",
    );
    expect(screen.getByRole("heading", { name: en.review.contextHeading })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: en.review.changeRequest })).toBeInTheDocument();
    expect(screen.getByText(en.review.confirmConsequence)).toBeInTheDocument();
    expect(screen.getByText(en.newTest.documentTypeLabels.contract)).toBeInTheDocument();
    expect(screen.queryByText(copy.review.contextHeading)).not.toBeInTheDocument();
  });
});

/**
 * T32.3 / #103: the primary before/after ("What the gateway did") is visible
 * by default -- no click -- right after "What you asked for", built only from
 * `preview.inspection`, and only when the INSPECTION capability is on. It is
 * never implied by the transparency (export/restore) or vault capabilities.
 */
describe("ReviewScreen -- primary before/after (T32.3 / #103)", () => {
  const SEGMENTS = [
    { action: null, category: null, original: "Relatório de ", disclosed: "Relatório de " },
    { action: "pseudonymize", category: "employee_name", original: "Maria Silva", disclosed: "PESSOA_7f3a" },
    { action: null, category: null, original: ", salário ", disclosed: ", salário " },
    { action: "generalize", category: "salary", original: "R$ 8.500,00", disclosed: "R$ 5.000-10.000" },
    { action: null, category: null, original: ", CPF ", disclosed: ", CPF " },
    { action: "remove", category: "cpf", original: "123.456.789-00", disclosed: "" },
    { action: null, category: null, original: " fim.", disclosed: " fim." },
  ];
  const AVAILABLE: DisclosureInspection = { available: true, unavailable_reason: null, segments: SEGMENTS };

  function renderReview(
    props: {
      inspection?: DisclosureInspection | null;
      status?: "allowed" | "blocked";
      demoInspectionEnabled?: boolean;
      demoTransparencyEnabled?: boolean;
      demoVaultExplorerEnabled?: boolean;
    } = {},
  ) {
    const { inspection = AVAILABLE, status = "allowed", ...flags } = props;
    return render(
      <ReviewScreen
        preview={preview([category({})], status, inspection)}
        executeError={null}
        onConfirm={vi.fn()}
        onEdit={vi.fn()}
        {...flags}
      />,
    );
  }

  it("is in the DOM without any click when inspection is enabled and available", () => {
    renderReview({ demoInspectionEnabled: true });

    const summary = screen.getByTestId("before-after-summary");
    expect(within(summary).getByRole("heading", { name: copy.beforeAfter.heading })).toBeInTheDocument();
    expect(within(screen.getByTestId("before-after-original")).getByText("Maria Silva")).toBeInTheDocument();
    expect(within(screen.getByTestId("before-after-disclosed")).getByText("PESSOA_7f3a")).toBeInTheDocument();
    expect(
      within(screen.getByTestId("before-after-disclosed")).getByText(copy.inspectionActions.removedMarker),
    ).toBeInTheDocument();
    expect(screen.getByText(copy.beforeAfter.disclosedCaptionReview)).toBeInTheDocument();
  });

  it("shows Original, the local transformation step, and the representation prepared for egress -- without an identity promise with the later execute call (#103 review, PR #108)", () => {
    renderReview({ demoInspectionEnabled: true });

    expect(screen.getByRole("heading", { name: copy.beforeAfter.originalHeading })).toBeInTheDocument();
    expect(screen.getByText(copy.beforeAfter.transformationStep)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: copy.beforeAfter.disclosedHeadingReview })).toBeInTheDocument();

    expect(document.body.textContent).not.toMatch(/Exatamente esta representação/);
    expect(document.body.textContent).not.toMatch(/cruza a fronteira.*confirmar/);
  });

  it("sits right after 'What you asked for' and before detected/local/sent, details, and Confirm", () => {
    renderReview({ demoInspectionEnabled: true });

    const order = [
      screen.getByRole("heading", { name: copy.review.contextHeading }),
      screen.getByTestId("before-after-summary"),
      screen.getByText(copy.sectionHeadings.whatWasDetected),
      screen.getByText(copy.review.willBeSentHeading),
      screen.getByText(copy.review.understandChangesToggle),
      screen.getByRole("button", { name: copy.review.confirmSend }),
    ];
    for (let i = 0; i < order.length - 1; i += 1) {
      expect(order[i].compareDocumentPosition(order[i + 1]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    }
  });

  it("does not need the detailed inspector: its content stays out of the DOM until opened", () => {
    renderReview({ demoInspectionEnabled: true });

    expect(screen.queryByText(copy.disclosureInspector.toggleLabel)).not.toBeInTheDocument();
    expect(screen.queryByText(copy.disclosureInspector.detailReasonLabel)).not.toBeInTheDocument();
  });

  it("shows no b0-b4 code, strategy, policy version or technical reason before the details are opened", () => {
    renderReview({ demoInspectionEnabled: true });

    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/\bb[0-4]\b/i);
    expect(text).not.toContain("recommended");
    expect(text).not.toMatch(/\bv1\b/);
    expect(text).not.toContain("detected by rule X");
  });

  it("renders nothing extra when inspection is null, and Review keeps working with the overview", () => {
    renderReview({ demoInspectionEnabled: true, inspection: null });

    expect(screen.queryByTestId("before-after-summary")).not.toBeInTheDocument();
    expect(screen.queryByText(copy.review.understandChangesToggle)).not.toBeInTheDocument();
    expect(screen.getByText(copy.review.willBeSentHeading)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: copy.review.confirmSend })).toBeInTheDocument();
  });

  it("fails closed when the inspection capability is off, even if the body carries an inspection", () => {
    renderReview({ demoInspectionEnabled: false });

    expect(screen.queryByTestId("before-after-summary")).not.toBeInTheDocument();
    expect(screen.queryByText(copy.review.understandChangesToggle)).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain("Maria Silva");
  });

  it("(0,1,0) transparency alone never shows the before/after, but keeps its own technical tools", () => {
    renderReview({ demoTransparencyEnabled: true });

    expect(screen.queryByTestId("before-after-summary")).not.toBeInTheDocument();
    expect(screen.getByText(copy.review.technicalToolsToggle)).toBeInTheDocument();
  });

  it("(0,0,1) the vault explorer alone never shows the before/after", () => {
    renderReview({ demoVaultExplorerEnabled: true });

    expect(screen.queryByTestId("before-after-summary")).not.toBeInTheDocument();
    expect(screen.getByText(copy.review.technicalToolsToggle)).toBeInTheDocument();
  });

  it("(1,0,0) the public posture: before/after shown, no export/restore and no Vault Explorer at all", () => {
    renderReview({ demoInspectionEnabled: true });

    expect(screen.getByTestId("before-after-summary")).toBeInTheDocument();
    expect(screen.queryByText(copy.review.technicalToolsToggle)).not.toBeInTheDocument();
    expect(screen.queryByText(copy.exportRestorePanel.exportButton)).not.toBeInTheDocument();
    expect(screen.queryByText(copy.vaultExplorerPanel.toggleLabel)).not.toBeInTheDocument();
  });

  it("a blocked preview explains no representation was released, with no sent column and no Confirm", () => {
    renderReview({
      demoInspectionEnabled: true,
      status: "blocked",
      inspection: { available: false, unavailable_reason: "blocked", segments: [] },
    });

    expect(screen.getByText(copy.beforeAfter.unavailableBlocked)).toBeInTheDocument();
    expect(screen.queryByTestId("before-after-disclosed")).not.toBeInTheDocument();
    expect(screen.queryByText(copy.beforeAfter.disclosedHeadingReview)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: copy.review.confirmSend })).not.toBeInTheDocument();
  });

  it("alignment_failed says the view could not be produced safely, inventing no before/after", () => {
    renderReview({
      demoInspectionEnabled: true,
      inspection: { available: false, unavailable_reason: "alignment_failed", segments: [] },
    });

    expect(screen.getByText(copy.beforeAfter.unavailableAlignmentFailed)).toBeInTheDocument();
    expect(screen.queryByTestId("before-after-original")).not.toBeInTheDocument();
  });

  it("renders the before/after in English under the en locale", async () => {
    await renderWithLocale(
      <ReviewScreen
        preview={preview([category({})], "allowed", AVAILABLE)}
        executeError={null}
        onConfirm={vi.fn()}
        onEdit={vi.fn()}
        demoInspectionEnabled
      />,
      "en",
    );

    expect(screen.getByRole("heading", { name: en.beforeAfter.heading })).toBeInTheDocument();
    expect(screen.getByText(en.beforeAfter.transformationStep)).toBeInTheDocument();
    expect(screen.getByText(en.review.understandChangesToggle)).toBeInTheDocument();

    // #103 review fix (PR #108): no identity promise with the later execute call.
    expect(document.body.textContent).not.toMatch(/Exactly this representation/);
    expect(document.body.textContent).not.toMatch(/crosses the boundary.*confirm/);
  });
});
