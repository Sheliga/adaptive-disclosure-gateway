import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CONTRACT_VERSION } from "@/lib/contracts";
import { copy } from "@/lib/copy";

import { VaultExplorerPanel } from "./VaultExplorerPanel";

function vaultExplorerBody(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    contract_version: CONTRACT_VERSION,
    scope: "session",
    entry_count: 1,
    entries: [
      {
        category: "employee_name",
        pseudonym: "PSEUDO-a1b2",
        original: "Ana Souza SECRET_ORIGINAL_VALUE",
        present: true,
      },
    ],
    ...overrides,
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

function stubFetch(handler: () => Response) {
  const fetchImpl: typeof fetch = () => Promise.resolve(handler());
  const fetchMock = vi.fn(fetchImpl);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("VaultExplorerPanel -- token null (feature enabled but unavailable for this decision)", () => {
  it("shows an unavailable note and makes no fetch call", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    render(<VaultExplorerPanel token={null} />);

    expect(screen.getByText(copy.vaultExplorerPanel.unavailableForDecision)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("VaultExplorerPanel -- collapsed by default", () => {
  it("makes no fetch call and renders no entry until opened", () => {
    const fetchMock = stubFetch(() => jsonResponse(vaultExplorerBody()));

    render(<VaultExplorerPanel token="vx1.token" />);

    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.queryByText("PSEUDO-a1b2")).not.toBeInTheDocument();
  });

  it("shows the heading, subtitle and disclaimer immediately", () => {
    render(<VaultExplorerPanel token="vx1.token" />);

    expect(screen.getByText(copy.vaultExplorerPanel.heading)).toBeInTheDocument();
    expect(screen.getByText(copy.vaultExplorerPanel.subtitle)).toBeInTheDocument();
    expect(screen.getByText(copy.vaultExplorerPanel.disclaimer)).toBeInTheDocument();
  });
});

describe("VaultExplorerPanel -- opening fetches and renders entries", () => {
  it("fetches exactly once on open and renders scope, entry count, category and pseudonym", async () => {
    const fetchMock = stubFetch(() => jsonResponse(vaultExplorerBody()));

    render(<VaultExplorerPanel token="vx1.token" />);
    await userEvent.click(screen.getByText(copy.vaultExplorerPanel.toggleLabel));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("PSEUDO-a1b2")).toBeInTheDocument();
    expect(screen.getByText(/Nome do funcionário/)).toBeInTheDocument();
    expect(screen.getByText(/entradas reversíveis/)).toHaveTextContent("1 entradas reversíveis");
  });

  it("sends the token only in the JSON body of a request to /api/demo/vault-explorer, never in the URL", async () => {
    const fetchMock = stubFetch(() => jsonResponse(vaultExplorerBody()));

    render(<VaultExplorerPanel token="vx1.SUPER_SECRET_TOKEN" />);
    await userEvent.click(screen.getByText(copy.vaultExplorerPanel.toggleLabel));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/demo/vault-explorer");
    expect(url).not.toContain("SUPER_SECRET_TOKEN");
    expect(init?.body).toContain("SUPER_SECRET_TOKEN");
  });

  it("originals are masked by default and absent from the DOM until the toggle is used", async () => {
    stubFetch(() => jsonResponse(vaultExplorerBody()));

    const { container } = render(<VaultExplorerPanel token="vx1.token" />);
    await userEvent.click(screen.getByText(copy.vaultExplorerPanel.toggleLabel));
    await screen.findByText("PSEUDO-a1b2");

    expect(container.innerHTML).not.toContain("SECRET_ORIGINAL_VALUE");
    expect(screen.getByText(copy.vaultExplorerPanel.maskedValuePlaceholder)).toBeInTheDocument();
  });

  it("reveals exactly the originals when the show-originals toggle is used, and hides them again on toggle-off", async () => {
    stubFetch(() => jsonResponse(vaultExplorerBody()));

    render(<VaultExplorerPanel token="vx1.token" />);
    await userEvent.click(screen.getByText(copy.vaultExplorerPanel.toggleLabel));
    await screen.findByText("PSEUDO-a1b2");

    await userEvent.click(screen.getByText(copy.vaultExplorerPanel.showOriginalsToggle));
    expect(screen.getByText("Ana Souza SECRET_ORIGINAL_VALUE")).toBeInTheDocument();

    await userEvent.click(screen.getByText(copy.vaultExplorerPanel.hideOriginalsToggle));
    expect(screen.queryByText("Ana Souza SECRET_ORIGINAL_VALUE")).not.toBeInTheDocument();
    expect(screen.getByText(copy.vaultExplorerPanel.maskedValuePlaceholder)).toBeInTheDocument();
  });

  it("shows the present status label for a present entry and the not-present label for an absent one", async () => {
    stubFetch(() =>
      jsonResponse(
        vaultExplorerBody({
          entries: [
            { category: "employee_name", pseudonym: "PSEUDO-a1b2", original: "Ana Souza", present: true },
            { category: "cpf", pseudonym: "PSEUDO-c3d4", original: null, present: false },
          ],
          entry_count: 2,
        }),
      ),
    );

    render(<VaultExplorerPanel token="vx1.token" />);
    await userEvent.click(screen.getByText(copy.vaultExplorerPanel.toggleLabel));
    await screen.findByText("PSEUDO-a1b2");

    expect(screen.getByText(copy.vaultExplorerPanel.presentLabel)).toBeInTheDocument();
    expect(screen.getByText(copy.vaultExplorerPanel.notPresentLabel)).toBeInTheDocument();
  });

  it("shows the zero-entries explanation when scope is null (B0/B1)", async () => {
    stubFetch(() => jsonResponse({ contract_version: CONTRACT_VERSION, scope: null, entry_count: 0, entries: [] }));

    render(<VaultExplorerPanel token="vx1.token" />);
    await userEvent.click(screen.getByText(copy.vaultExplorerPanel.toggleLabel));

    expect(await screen.findByText(copy.vaultExplorerPanel.zeroEntriesMessage)).toBeInTheDocument();
  });
});

describe("VaultExplorerPanel -- errors", () => {
  it("shows a dedicated message for a 400 VaultExplorerReferenceError", async () => {
    stubFetch(() =>
      jsonResponse(
        {
          detail: "vault explorer reference is invalid, malformed, expired, or was not issued by this process",
          kind: "VaultExplorerReferenceError",
        },
        400,
      ),
    );

    render(<VaultExplorerPanel token="vx1.bad" />);
    await userEvent.click(screen.getByText(copy.vaultExplorerPanel.toggleLabel));

    expect(await screen.findByText(copy.errors.vaultExplorerReferenceInvalid)).toBeInTheDocument();
  });

  it("shows a dedicated message for a 404 DemoVaultExplorerDisabled", async () => {
    stubFetch(() => jsonResponse({ detail: "not found", kind: "DemoVaultExplorerDisabled" }, 404));

    render(<VaultExplorerPanel token="vx1.token" />);
    await userEvent.click(screen.getByText(copy.vaultExplorerPanel.toggleLabel));

    expect(await screen.findByText(copy.errors.demoVaultExplorerDisabled)).toBeInTheDocument();
  });
});

describe("VaultExplorerPanel -- closing discards fetched data", () => {
  it("clears rendered entries on close and re-fetches on the next open", async () => {
    const fetchMock = stubFetch(() => jsonResponse(vaultExplorerBody()));

    render(<VaultExplorerPanel token="vx1.token" />);
    const toggle = () => screen.getByText(copy.vaultExplorerPanel.toggleLabel);

    await userEvent.click(toggle());
    await screen.findByText("PSEUDO-a1b2");
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await userEvent.click(toggle());
    expect(screen.queryByText("PSEUDO-a1b2")).not.toBeInTheDocument();

    await userEvent.click(toggle());
    await screen.findByText("PSEUDO-a1b2");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("unmounting discards any fetched data (no leak across a fresh mount)", async () => {
    stubFetch(() => jsonResponse(vaultExplorerBody()));

    const { unmount } = render(<VaultExplorerPanel token="vx1.token" />);
    await userEvent.click(screen.getByText(copy.vaultExplorerPanel.toggleLabel));
    await screen.findByText("PSEUDO-a1b2");
    unmount();

    render(<VaultExplorerPanel token="vx1.token" />);
    expect(screen.queryByText("PSEUDO-a1b2")).not.toBeInTheDocument();
  });
});

describe("VaultExplorerPanel -- adversarial no-leak tests", () => {
  it("never passes the token, a pseudonym, or an original through Storage.setItem, cookies, history navigation, window.location, or console", async () => {
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem");
    const pushStateSpy = vi.spyOn(history, "pushState");
    const replaceStateSpy = vi.spyOn(history, "replaceState");
    const consoleLogSpy = vi.spyOn(console, "log").mockImplementation(() => {});
    const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const consoleWarnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    const consoleInfoSpy = vi.spyOn(console, "info").mockImplementation(() => {});
    const consoleDebugSpy = vi.spyOn(console, "debug").mockImplementation(() => {});
    const cookieSetterCalls: string[] = [];
    Object.defineProperty(document, "cookie", {
      configurable: true,
      get: () => "",
      set: (value: string) => {
        cookieSetterCalls.push(value);
      },
    });

    stubFetch(() => jsonResponse(vaultExplorerBody()));

    render(<VaultExplorerPanel token="vx1.SESSION_SECRET_TOKEN" />);
    await userEvent.click(screen.getByText(copy.vaultExplorerPanel.toggleLabel));
    await screen.findByText("PSEUDO-a1b2");
    await userEvent.click(screen.getByText(copy.vaultExplorerPanel.showOriginalsToggle));
    await screen.findByText("Ana Souza SECRET_ORIGINAL_VALUE");
    await userEvent.click(screen.getByText(copy.vaultExplorerPanel.hideOriginalsToggle));
    await userEvent.click(screen.getByText(copy.vaultExplorerPanel.toggleLabel));

    const sensitiveMarkers = ["SESSION_SECRET_TOKEN", "SECRET_ORIGINAL_VALUE", "PSEUDO-a1b2"];

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
    assertNoLeak(consoleInfoSpy.mock.calls);
    assertNoLeak(consoleDebugSpy.mock.calls);

    for (const marker of sensitiveMarkers) {
      expect(cookieSetterCalls.join("\n")).not.toContain(marker);
    }
    expect(window.location.href).not.toContain("SESSION_SECRET_TOKEN");
  });

  it("never renders a mapping-shaped table pairing a pseudonym with its original", async () => {
    stubFetch(() => jsonResponse(vaultExplorerBody()));

    const { container } = render(<VaultExplorerPanel token="vx1.token" />);
    await userEvent.click(screen.getByText(copy.vaultExplorerPanel.toggleLabel));
    await screen.findByText("PSEUDO-a1b2");

    expect(container.querySelectorAll("table").length).toBe(0);
  });
});
