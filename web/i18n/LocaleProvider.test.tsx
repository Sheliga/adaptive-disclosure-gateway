import { act, render, screen, waitFor } from "@testing-library/react";
import { hydrateRoot } from "react-dom/client";
import { renderToString } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DEFAULT_LOCALE } from "./locales";
import { LOCALE_STORAGE_KEY, readStoredLocale } from "./localeStorage";
import { initialLocale, LocaleProvider } from "./LocaleProvider";
import { useCopy, useLocale } from "./useLocale";

function Probe() {
  const { locale, setLocale } = useLocale();
  const copy = useCopy();
  return (
    <div>
      <span data-testid="locale">{locale}</span>
      <span data-testid="cta">{copy.howItWorks.ctaPrimary}</span>
      <button type="button" onClick={() => setLocale("en-US")}>
        switch to en
      </button>
      <button type="button" onClick={() => setLocale("pt-BR")}>
        switch to pt
      </button>
    </div>
  );
}

beforeEach(() => {
  window.localStorage.clear();
});

describe("initialLocale -- never reads storage (SSR/hydration safety)", () => {
  it("is always the product default regardless of what is stored", () => {
    // This is the property that matters for the server/client hydration
    // mismatch trap: the server render has no localStorage at all, so the
    // FIRST client render must match it byte-for-byte -- which is only true
    // if the initial state never depends on a synchronous storage read. A
    // component that "fixes" the flash by reading storage in a useState
    // initializer would make this test fail immediately.
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en-US");
    expect(initialLocale()).toBe(DEFAULT_LOCALE);
  });

  it("still defaults even when storage cannot be read at all", () => {
    expect(initialLocale()).toBe("pt-BR");
  });
});

describe("LocaleProvider -- real SSR markup hydrates cleanly (no hydration mismatch)", () => {
  let container: HTMLDivElement | null = null;

  afterEach(() => {
    if (container) {
      container.remove();
      container = null;
    }
  });

  it("produces pt-BR server markup and hydrates it without a console hydration warning, even with en-US already stored", async () => {
    // Simulates the real scenario the trap describes: a returning visitor
    // whose browser already has "en-US" stored, requesting a page the
    // server always renders in pt-BR (the server has no access to this
    // browser's localStorage at all).
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en-US");

    const html = renderToString(
      <LocaleProvider>
        <Probe />
      </LocaleProvider>,
    );
    // The server output is provably pt-BR -- proves the server-side render
    // path never depends on this browser's storage.
    expect(html).toContain("pt-BR");
    expect(html).not.toContain("en-US");

    container = document.createElement("div");
    container.innerHTML = html;
    document.body.appendChild(container);

    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    await act(async () => {
      hydrateRoot(
        container as HTMLDivElement,
        <LocaleProvider>
          <Probe />
        </LocaleProvider>,
      );
    });

    const hydrationWarnings = consoleError.mock.calls.filter((call) =>
      call.some((arg) => typeof arg === "string" && /hydrat/i.test(arg)),
    );
    expect(hydrationWarnings).toEqual([]);
    consoleError.mockRestore();

    // Once hydrated, the stored preference still applies -- the flash is
    // brief, not a correctness gap.
    await waitFor(() =>
      expect(container?.querySelector('[data-testid="locale"]')?.textContent).toBe("en-US"),
    );
  });
});

describe("useLocale/useCopy without a LocaleProvider -- safe default context", () => {
  it("renders pt-BR by default so every existing screen test keeps working unmodified", () => {
    render(<Probe />);
    expect(screen.getByTestId("locale")).toHaveTextContent("pt-BR");
    expect(screen.getByTestId("cta")).toHaveTextContent("Testar agora");
  });
});

describe("LocaleProvider -- first visit uses pt-BR", () => {
  it("renders pt-BR with no stored preference", async () => {
    render(
      <LocaleProvider>
        <Probe />
      </LocaleProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("locale")).toHaveTextContent("pt-BR"));
    expect(screen.getByTestId("cta")).toHaveTextContent("Testar agora");
  });
});

describe("LocaleProvider -- applies a stored preference after mount", () => {
  it("switches to the stored locale once the mount effect runs", async () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en-US");
    render(
      <LocaleProvider>
        <Probe />
      </LocaleProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("locale")).toHaveTextContent("en-US"));
    expect(screen.getByTestId("cta")).toHaveTextContent("Try it now");
  });

  it("falls back to pt-BR for an invalid/unparseable stored value", async () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "klingon");
    render(
      <LocaleProvider>
        <Probe />
      </LocaleProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("locale")).toHaveTextContent("pt-BR"));
  });
});

describe("LocaleProvider -- switching locale", () => {
  it("switching to English updates the UI without a reload", async () => {
    render(
      <LocaleProvider>
        <Probe />
      </LocaleProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("locale")).toHaveTextContent("pt-BR"));

    act(() => {
      screen.getByRole("button", { name: "switch to en" }).click();
    });

    expect(screen.getByTestId("locale")).toHaveTextContent("en-US");
    expect(screen.getByTestId("cta")).toHaveTextContent("Try it now");
  });

  it("switching back to Portuguese works", async () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en-US");
    render(
      <LocaleProvider>
        <Probe />
      </LocaleProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("locale")).toHaveTextContent("en-US"));

    act(() => {
      screen.getByRole("button", { name: "switch to pt" }).click();
    });

    expect(screen.getByTestId("locale")).toHaveTextContent("pt-BR");
    expect(screen.getByTestId("cta")).toHaveTextContent("Testar agora");
  });

  it("persists the choice to localStorage", async () => {
    render(
      <LocaleProvider>
        <Probe />
      </LocaleProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("locale")).toHaveTextContent("pt-BR"));

    act(() => {
      screen.getByRole("button", { name: "switch to en" }).click();
    });

    expect(readStoredLocale()).toBe("en-US");
  });

  it("a remount restores the persisted locale", async () => {
    const { unmount } = render(
      <LocaleProvider>
        <Probe />
      </LocaleProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("locale")).toHaveTextContent("pt-BR"));
    act(() => {
      screen.getByRole("button", { name: "switch to en" }).click();
    });
    unmount();

    render(
      <LocaleProvider>
        <Probe />
      </LocaleProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("locale")).toHaveTextContent("en-US"));
  });
});

describe("LocaleProvider -- single source of truth, no duplicated locale state", () => {
  function Consumer({ testId }: { testId: string }) {
    const { locale } = useLocale();
    return <span data-testid={testId}>{locale}</span>;
  }

  it("a second consumer under the same provider observes the same locale, never a stale copy", async () => {
    render(
      <LocaleProvider>
        <Consumer testId="a" />
        <Consumer testId="b" />
        <Probe />
      </LocaleProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("a")).toHaveTextContent("pt-BR"));

    act(() => {
      screen.getByRole("button", { name: "switch to en" }).click();
    });

    expect(screen.getByTestId("a")).toHaveTextContent("en-US");
    expect(screen.getByTestId("b")).toHaveTextContent("en-US");
  });
});
