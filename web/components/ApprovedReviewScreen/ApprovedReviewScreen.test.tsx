import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { DisclosureInspection, PreviewResponse } from "@/lib/contracts";
import { copy } from "@/lib/copy";
import { initialComposeState } from "@/lib/flow";

import { ApprovedReviewScreen } from "./ApprovedReviewScreen";

beforeEach(() => {
  window.localStorage.clear();
});

const AVAILABLE: DisclosureInspection = {
  available: true,
  unavailable_reason: null,
  segments: [
    { action: null, category: null, original: "Relatório de ", disclosed: "Relatório de " },
    { action: "pseudonymize", category: "employee_name", original: "Maria Silva", disclosed: "PESSOA_7f3a" },
    { action: "remove", category: "cpf", original: "123.456.789-00", disclosed: "" },
  ],
};

function preview(inspection: DisclosureInspection | null): PreviewResponse {
  return {
    contract_version: "t20-application-api-v1",
    summary: { status: "allowed", categories: [], detected_span_count: 2, detected_categories: [] },
    external_payload: "Relatório de PESSOA_7f3a",
    payload_byte_count: 24,
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
    vault_explorer_token: "opaque-token",
  };
}

function renderApproved(inspection: DisclosureInspection | null, demoInspectionEnabled?: boolean) {
  const onGoToResult = vi.fn();
  render(
    <ApprovedReviewScreen
      compose={initialComposeState}
      preview={preview(inspection)}
      examples={null}
      onGoToResult={onGoToResult}
      demoInspectionEnabled={demoInspectionEnabled}
    />,
  );
  return onGoToResult;
}

/**
 * T32.3 / #103: the read-only Approved Review (#102) also shows what was
 * approved to cross the boundary, as the primary before/after -- while
 * keeping every #102 property: no Confirm, no Change, no resend, no token,
 * no re-identification tools, and Result reachable only through Forward.
 */
describe("ApprovedReviewScreen -- approved before/after (T32.3 / #103)", () => {
  it("shows the approved before/after by default when inspection is enabled and available", () => {
    renderApproved(AVAILABLE, true);

    const summary = screen.getByTestId("before-after-summary");
    expect(within(summary).getByRole("heading", { name: copy.beforeAfter.heading })).toBeInTheDocument();
    expect(within(summary).getByText(copy.beforeAfter.disclosedHeadingApproved)).toBeInTheDocument();
    expect(within(screen.getByTestId("before-after-disclosed")).getByText("PESSOA_7f3a")).toBeInTheDocument();
    expect(
      within(screen.getByTestId("before-after-disclosed")).getByText(copy.inspectionActions.removedMarker),
    ).toBeInTheDocument();
    expect(screen.queryByText(copy.beforeAfter.disclosedHeadingReview)).not.toBeInTheDocument();
  });

  it("places it after the request context and before the detected/sent overview", () => {
    renderApproved(AVAILABLE, true);

    const context = screen.getByRole("heading", { name: copy.review.contextHeading });
    const summary = screen.getByTestId("before-after-summary");
    const detected = screen.getByText(copy.sectionHeadings.whatWasDetected);
    expect(context.compareDocumentPosition(summary) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(summary.compareDocumentPosition(detected) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("keeps the #102 read-only contract: the only action is 'go to result', wired to onGoToResult", async () => {
    const onGoToResult = renderApproved(AVAILABLE, true);

    expect(screen.queryByRole("button", { name: copy.review.confirmSend })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: copy.review.changeRequest })).not.toBeInTheDocument();
    expect(screen.getAllByRole("button")).toHaveLength(1);

    await userEvent.click(screen.getByRole("button", { name: copy.approvedReview.goToResult }));

    expect(onGoToResult).toHaveBeenCalledTimes(1);
  });

  it("offers no re-identification or technical tools and no detailed inspector", () => {
    renderApproved(AVAILABLE, true);

    expect(screen.queryByText(copy.review.technicalToolsToggle)).not.toBeInTheDocument();
    expect(screen.queryByText(copy.exportRestorePanel.exportButton)).not.toBeInTheDocument();
    expect(screen.queryByText(copy.vaultExplorerPanel.toggleLabel)).not.toBeInTheDocument();
    expect(screen.queryByText(copy.review.understandChangesToggle)).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain("opaque-token");
  });

  it("renders no before/after when the inspection capability is off (default), even with an inspection body", () => {
    renderApproved(AVAILABLE);

    expect(screen.queryByTestId("before-after-summary")).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain("Maria Silva");
  });

  it("renders no before/after when inspection is null", () => {
    renderApproved(null, true);

    expect(screen.queryByTestId("before-after-summary")).not.toBeInTheDocument();
    expect(screen.getByText(copy.approvedReview.sentHeading)).toBeInTheDocument();
  });

  it("an unavailable inspection shows its plain message and no fabricated columns", () => {
    renderApproved({ available: false, unavailable_reason: "alignment_failed", segments: [] }, true);

    expect(screen.getByText(copy.beforeAfter.unavailableAlignmentFailed)).toBeInTheDocument();
    expect(screen.queryByTestId("before-after-original")).not.toBeInTheDocument();
  });
});
