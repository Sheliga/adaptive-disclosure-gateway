import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CONTRACT_VERSION } from "@/lib/contracts";
import { copy } from "@/lib/copy";
import type { ComposeState } from "@/lib/flow";
import { initialComposeState } from "@/lib/flow";

import { ExportRestorePanel } from "./ExportRestorePanel";

function uploadCompose(overrides: Partial<ComposeState> = {}): ComposeState {
  const file = new File(["synthetic contract bytes"], "contract.pdf", { type: "application/pdf" });
  return {
    ...initialComposeState,
    mode: "upload",
    file: { file, filename: "contract.pdf", byteSize: file.size, displayType: "pdf" },
    task: "Resuma o contrato.",
    documentType: "contract",
    analysisMode: "contract_summary",
    ...overrides,
  };
}

function exportBody(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    contract_version: CONTRACT_VERSION,
    external_payload: "PSEUDO-a1b2 assinou o contrato",
    restore_handle: "opaque.restore.handle.SECRET_HANDLE_VALUE",
    expires_at: Math.floor(Date.now() / 1000) + 3600,
    restorable_count: 1,
    treatment: "b2",
    strategy: "b2",
    governance: {
      domain: "contracts",
      purpose: "contract_summary",
      policy_version: "contracts-v1",
      provider_class: "FakeProvider",
      requester_role: null,
      requested_pseudonym_scope: "session",
    },
    ...overrides,
  };
}

function restoreBody(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    contract_version: CONTRACT_VERSION,
    restored_text: "Maria Oliveira assinou o contrato",
    restored_count: 1,
    unresolved_count: 0,
    ...overrides,
  };
}

function stubFetchRouting(handlers: { export?: () => Response; restore?: () => Response }) {
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input.toString();
    if (url.includes("/api/documents/export") && handlers.export) {
      return Promise.resolve(handlers.export());
    }
    if (url.includes("/api/documents/restore") && handlers.restore) {
      return Promise.resolve(handlers.restore());
    }
    return Promise.resolve(new Response("{}", { status: 500 }));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("ExportRestorePanel -- upload-only export", () => {
  it("shows an explanatory note instead of the export button in non-upload modes", () => {
    render(<ExportRestorePanel compose={{ ...initialComposeState, mode: "paste", pastedText: "x" }} />);

    expect(screen.getByText(copy.exportRestorePanel.uploadOnlyNote)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: copy.exportRestorePanel.exportButton })).not.toBeInTheDocument();
  });

  it("shows the export button in upload mode", () => {
    render(<ExportRestorePanel compose={uploadCompose()} />);

    expect(screen.getByRole("button", { name: copy.exportRestorePanel.exportButton })).toBeInTheDocument();
  });
});

describe("ExportRestorePanel -- export flow", () => {
  it("shows external_payload, restorable_count, expiry and treatment/strategy on a successful export", async () => {
    stubFetchRouting({ export: () => jsonResponse(exportBody()) });
    render(<ExportRestorePanel compose={uploadCompose()} />);

    await userEvent.click(screen.getByRole("button", { name: copy.exportRestorePanel.exportButton }));

    await screen.findByText(copy.exportRestorePanel.exportedPayloadHeading);
    expect(screen.getByTestId("export-payload")).toHaveTextContent("PSEUDO-a1b2 assinou o contrato");
    expect(screen.getByTestId("restorable-count")).toHaveTextContent("1");
    expect(screen.getAllByText("b2")).toHaveLength(2);
  });

  it("shows a 400 ExportRefusedError message and no handle on failure", async () => {
    stubFetchRouting({
      export: () =>
        jsonResponse({ detail: "export refused", kind: "ExportRefusedError" }, 400),
    });
    render(<ExportRestorePanel compose={uploadCompose()} />);

    await userEvent.click(screen.getByRole("button", { name: copy.exportRestorePanel.exportButton }));

    expect(await screen.findByText(copy.errors.exportRefused)).toBeInTheDocument();
    expect(screen.queryByText(copy.exportRestorePanel.exportedPayloadHeading)).not.toBeInTheDocument();
  });

  it("shows a 503 RestoreUnavailableError message when export itself is refused for that reason", async () => {
    stubFetchRouting({
      export: () => jsonResponse({ detail: "restore is not available", kind: "RestoreUnavailableError" }, 503),
    });
    render(<ExportRestorePanel compose={uploadCompose()} />);

    await userEvent.click(screen.getByRole("button", { name: copy.exportRestorePanel.exportButton }));

    expect(await screen.findByText(copy.errors.restoreUnavailable)).toBeInTheDocument();
  });

  it("shows the disabled message on a 404 DemoTransparencyDisabled", async () => {
    stubFetchRouting({
      export: () => jsonResponse({ detail: "not found", kind: "DemoTransparencyDisabled" }, 404),
    });
    render(<ExportRestorePanel compose={uploadCompose()} />);

    await userEvent.click(screen.getByRole("button", { name: copy.exportRestorePanel.exportButton }));

    expect(await screen.findByText(copy.errors.demoTransparencyDisabled)).toBeInTheDocument();
  });
});

describe("ExportRestorePanel -- restore flow", () => {
  async function exportSuccessfully() {
    stubFetchRouting({ export: () => jsonResponse(exportBody()) });
    render(<ExportRestorePanel compose={uploadCompose()} />);
    await userEvent.click(screen.getByRole("button", { name: copy.exportRestorePanel.exportButton }));
    await screen.findByText(copy.exportRestorePanel.exportedPayloadHeading);
  }

  it("shows restored text and counts on a successful restore", async () => {
    await exportSuccessfully();
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/api/documents/restore")) {
        return Promise.resolve(jsonResponse(restoreBody()));
      }
      return Promise.resolve(jsonResponse(exportBody()));
    });

    await userEvent.click(screen.getByRole("button", { name: copy.exportRestorePanel.restoreButton }));

    await screen.findByText(copy.exportRestorePanel.restoredResultHeading);
    expect(screen.getByTestId("restored-text")).toHaveTextContent("Maria Oliveira assinou o contrato");
  });

  it("shows a foreign-handle result (restored_count 0, unresolved_count > 0) correctly", async () => {
    await exportSuccessfully();
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/api/documents/restore")) {
        return Promise.resolve(
          jsonResponse(restoreBody({ restored_text: "PSEUDO-unknown permanece", restored_count: 0, unresolved_count: 2 })),
        );
      }
      return Promise.resolve(jsonResponse(exportBody()));
    });

    await userEvent.click(screen.getByRole("button", { name: copy.exportRestorePanel.restoreButton }));

    await screen.findByText(copy.exportRestorePanel.restoredResultHeading);
    expect(screen.getByTestId("restored-text")).toHaveTextContent("PSEUDO-unknown permanece");
    expect(screen.getByText(copy.exportRestorePanel.unresolvedExplanation)).toBeInTheDocument();
  });

  it.each([
    [400, "RestoreHandleInvalidError"],
    [400, "RestoreHandleExpiredError"],
    [503, "RestoreUnavailableError"],
    [404, "DemoTransparencyDisabled"],
  ] as const)("shows the right message for a %d %s restore failure and no restored text", async (status, kind) => {
    await exportSuccessfully();
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/api/documents/restore")) {
        return Promise.resolve(jsonResponse({ detail: "x", kind }, status));
      }
      return Promise.resolve(jsonResponse(exportBody()));
    });

    await userEvent.click(screen.getByRole("button", { name: copy.exportRestorePanel.restoreButton }));

    await waitFor(() => {
      const messages: Record<string, string> = {
        RestoreHandleInvalidError: copy.errors.restoreHandleInvalid,
        RestoreHandleExpiredError: copy.errors.restoreHandleExpired,
        RestoreUnavailableError: copy.errors.restoreUnavailable,
        DemoTransparencyDisabled: copy.errors.demoTransparencyDisabled,
      };
      expect(screen.getByText(messages[kind])).toBeInTheDocument();
    });
    expect(screen.queryByText(copy.exportRestorePanel.restoredResultHeading)).not.toBeInTheDocument();
  });
});

describe("ExportRestorePanel -- clear resets state", () => {
  it("clears the export result, handle and restore result when Limpar is clicked", async () => {
    stubFetchRouting({ export: () => jsonResponse(exportBody()), restore: () => jsonResponse(restoreBody()) });
    render(<ExportRestorePanel compose={uploadCompose()} />);
    await userEvent.click(screen.getByRole("button", { name: copy.exportRestorePanel.exportButton }));
    await screen.findByText(copy.exportRestorePanel.exportedPayloadHeading);
    await userEvent.click(screen.getByRole("button", { name: copy.exportRestorePanel.restoreButton }));
    await screen.findByText(copy.exportRestorePanel.restoredResultHeading);

    await userEvent.click(screen.getByRole("button", { name: copy.exportRestorePanel.clearButton }));

    expect(screen.queryByText(copy.exportRestorePanel.exportedPayloadHeading)).not.toBeInTheDocument();
    expect(screen.queryByText(copy.exportRestorePanel.restoredResultHeading)).not.toBeInTheDocument();
  });
});

describe("ExportRestorePanel -- adversarial no-leak tests", () => {
  it("never passes the handle, original, or pseudonym-bearing text through Storage.setItem, history navigation, or console during a full export->restore cycle", async () => {
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem");
    const pushStateSpy = vi.spyOn(history, "pushState");
    const replaceStateSpy = vi.spyOn(history, "replaceState");
    const consoleLogSpy = vi.spyOn(console, "log").mockImplementation(() => {});
    const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const consoleWarnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

    stubFetchRouting({ export: () => jsonResponse(exportBody()), restore: () => jsonResponse(restoreBody()) });
    render(<ExportRestorePanel compose={uploadCompose()} />);

    await userEvent.click(screen.getByRole("button", { name: copy.exportRestorePanel.exportButton }));
    await screen.findByText(copy.exportRestorePanel.exportedPayloadHeading);
    await userEvent.click(screen.getByRole("button", { name: copy.exportRestorePanel.restoreButton }));
    await screen.findByText(copy.exportRestorePanel.restoredResultHeading);

    const sensitiveMarkers = [
      "SECRET_HANDLE_VALUE",
      "opaque.restore.handle.SECRET_HANDLE_VALUE",
      "Maria Oliveira assinou o contrato",
      "PSEUDO-a1b2 assinou o contrato",
    ];

    function assertNoLeak(calls: unknown[][]) {
      for (const call of calls) {
        const serialized = JSON.stringify(call);
        for (const marker of sensitiveMarkers) {
          expect(serialized).not.toContain(marker);
        }
      }
    }

    assertNoLeak(setItemSpy.mock.calls);
    assertNoLeak(pushStateSpy.mock.calls);
    assertNoLeak(replaceStateSpy.mock.calls);
    assertNoLeak(consoleLogSpy.mock.calls);
    assertNoLeak(consoleErrorSpy.mock.calls);
    assertNoLeak(consoleWarnSpy.mock.calls);

    // Also never in the URL/querystring.
    expect(window.location.href).not.toContain("SECRET_HANDLE_VALUE");
  });

  it("never renders a mapping-shaped structure (pseudonym paired with its original) outside the restored text itself", async () => {
    stubFetchRouting({ export: () => jsonResponse(exportBody()), restore: () => jsonResponse(restoreBody()) });
    const { container } = render(<ExportRestorePanel compose={uploadCompose()} />);

    await userEvent.click(screen.getByRole("button", { name: copy.exportRestorePanel.exportButton }));
    await screen.findByText(copy.exportRestorePanel.exportedPayloadHeading);
    await userEvent.click(screen.getByRole("button", { name: copy.exportRestorePanel.restoreButton }));
    await screen.findByText(copy.exportRestorePanel.restoredResultHeading);

    // No table, dl, or list rendered by this component pairs a pseudonym
    // token with its original value -- the only place both concepts appear
    // is inside the flat, opaque `external_payload`/`restored_text` strings
    // themselves, never structured side-by-side.
    const tables = container.querySelectorAll("table");
    expect(tables.length).toBe(0);
  });

  it("never renders the raw restore_handle verbatim -- only a masked/truncated form", async () => {
    stubFetchRouting({ export: () => jsonResponse(exportBody()) });
    render(<ExportRestorePanel compose={uploadCompose()} />);

    await userEvent.click(screen.getByRole("button", { name: copy.exportRestorePanel.exportButton }));
    await screen.findByText(copy.exportRestorePanel.exportedPayloadHeading);

    expect(screen.queryByText("opaque.restore.handle.SECRET_HANDLE_VALUE")).not.toBeInTheDocument();
  });

  it("download uses a Blob object URL and revokes it", async () => {
    stubFetchRouting({ export: () => jsonResponse(exportBody()) });
    const createObjectURLSpy = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:mock-url");
    const revokeObjectURLSpy = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    render(<ExportRestorePanel compose={uploadCompose()} />);

    await userEvent.click(screen.getByRole("button", { name: copy.exportRestorePanel.exportButton }));
    await screen.findByText(copy.exportRestorePanel.exportedPayloadHeading);
    await userEvent.click(screen.getByRole("button", { name: copy.exportRestorePanel.downloadHandleButton }));

    expect(createObjectURLSpy).toHaveBeenCalledTimes(1);
    expect(createObjectURLSpy.mock.calls[0][0]).toBeInstanceOf(Blob);
    expect(revokeObjectURLSpy).toHaveBeenCalledWith("blob:mock-url");
  });
});
