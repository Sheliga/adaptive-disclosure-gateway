import { act, render, screen, waitFor } from "@testing-library/react";
import { hydrateRoot } from "react-dom/client";
import { renderToString } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DEFAULT_LOCALE } from "./locales";
import { LOCALE_STORAGE_KEY, readStoredLocale } from "./localeStorage";
import { initialLocale, LocaleProvider, resetVolatileLocaleForTests } from "./LocaleProvider";
import { useCopy, useLocale } from "./useLocale";

/**
 * `window.localStorage.setItem = () => { throw ... }` looks like a mock but
 * is NOT one: `Storage` is a legacy platform object whose own [[Set]] (and
 * [[DefineOwnProperty]]) treat a plain assignment on the INSTANCE as writing
 * a storage entry literally named "setItem"/"getItem", never as replacing
 * the method -- the real method call still resolves through the prototype
 * and succeeds. A test using that pattern would pass even with the
 * production `try/catch` deleted, because the "mocked" method never
 * actually throws. Overriding the method on
 * `Object.getPrototypeOf(window.localStorage)` goes through ordinary
 * [[DefineOwnProperty]] instead and genuinely intercepts the call -- see
 * `localeStorage.test.ts` for the same helper and a longer note.
 */
function mockStorageMethodToThrow(method: "getItem" | "setItem") {
  const proto = Object.getPrototypeOf(window.localStorage) as Storage;
  return vi.spyOn(proto, method).mockImplementation(() => {
    throw new Error("blocked");
  });
}

function Probe() {
  const { locale, setLocale } = useLocale();
  const copy = useCopy();
  return (
    <div>
      <span data-testid="locale">{locale}</span>
      <span data-testid="cta">{copy.howItWorks.ctaPrimary}</span>
      <button type="button" onClick={() => setLocale("en")}>
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
  // `volatileLocale` in LocaleProvider.tsx is module-level state, not React
  // state -- it survives across `it()` blocks within this file unless
  // explicitly cleared. See the "test isolation" describe below for a
  // regression test that would catch a missing reset here.
  resetVolatileLocaleForTests();
});

describe("initialLocale -- never reads storage (SSR/hydration safety)", () => {
  it("is always the product default regardless of what is stored", () => {
    // This is the property that matters for the server/client hydration
    // mismatch trap: the server render has no localStorage at all, so the
    // FIRST client render must match it byte-for-byte -- which is only true
    // if the initial state never depends on a synchronous storage read. A
    // component that "fixes" the flash by reading storage in a useState
    // initializer would make this test fail immediately.
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en");
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

  it("produces pt-BR server markup and hydrates it without a console hydration warning, even with en already stored", async () => {
    // Simulates the real scenario the trap describes: a returning visitor
    // whose browser already has "en" stored, requesting a page the server
    // always renders in pt-BR (the server has no access to this browser's
    // localStorage at all).
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en");

    const html = renderToString(
      <LocaleProvider>
        <Probe />
      </LocaleProvider>,
    );

    container = document.createElement("div");
    container.innerHTML = html;
    document.body.appendChild(container);

    // The server output is provably pt-BR -- proves the server-side render
    // path never depends on this browser's storage. Checked through the DOM
    // (not a raw substring match on `html`) because `Probe`'s own static
    // button label ("switch to en") legitimately contains "en" regardless of
    // which locale actually rendered, so a substring check would not catch
    // a regression here.
    expect(container.querySelector('[data-testid="locale"]')?.textContent).toBe("pt-BR");

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
    await waitFor(() => expect(container?.querySelector('[data-testid="locale"]')?.textContent).toBe("en"));
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
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en");
    render(
      <LocaleProvider>
        <Probe />
      </LocaleProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("locale")).toHaveTextContent("en"));
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

  /**
   * Regression pin: `en-US` was the first (incorrect) implementation of the
   * English locale code. A value stored under that old code must be treated
   * as unsupported garbage, exactly like `klingon` above, never silently
   * upgraded to `en`.
   */
  it("falls back to pt-BR for a stored en-US -- the old code is not an alias for en", async () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en-US");
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

    expect(screen.getByTestId("locale")).toHaveTextContent("en");
    expect(screen.getByTestId("cta")).toHaveTextContent("Try it now");
  });

  it("switching back to Portuguese works", async () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en");
    render(
      <LocaleProvider>
        <Probe />
      </LocaleProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("locale")).toHaveTextContent("en"));

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

    expect(readStoredLocale()).toBe("en");
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
    await waitFor(() => expect(screen.getByTestId("locale")).toHaveTextContent("en"));
  });
});

describe("LocaleProvider -- keeps <html lang> in sync with the active locale (client-side only)", () => {
  it("sets documentElement.lang to pt-BR on mount and to en after switching", async () => {
    render(
      <LocaleProvider>
        <Probe />
      </LocaleProvider>,
    );
    await waitFor(() => expect(document.documentElement.lang).toBe("pt-BR"));

    act(() => {
      screen.getByRole("button", { name: "switch to en" }).click();
    });

    await waitFor(() => expect(document.documentElement.lang).toBe("en"));
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

    expect(screen.getByTestId("a")).toHaveTextContent("en");
    expect(screen.getByTestId("b")).toHaveTextContent("en");
  });
});

/**
 * Blocker fix: a persistence failure must not prevent the locale from
 * changing in the current session. Before the fix, `getSnapshot` had no
 * source of truth besides storage (`readStoredLocale() ?? DEFAULT_LOCALE`),
 * so a throwing `setItem` left `setLocale` writing nothing, `notify()`
 * firing, and every consumer re-reading the SAME old value -- the click
 * silently did nothing. `volatileLocale` (an in-memory session value,
 * checked before storage) is what makes these pass.
 */
describe("LocaleProvider -- a persistence failure does not prevent the locale from changing this session", () => {
  it("switches to English when localStorage.setItem throws, without throwing itself, and the UI reflects it", async () => {
    const spy = mockStorageMethodToThrow("setItem");

    try {
      render(
        <LocaleProvider>
          <Probe />
        </LocaleProvider>,
      );
      await waitFor(() => expect(screen.getByTestId("locale")).toHaveTextContent("pt-BR"));

      expect(() => {
        act(() => {
          screen.getByRole("button", { name: "switch to en" }).click();
        });
      }).not.toThrow();

      expect(spy).toHaveBeenCalled(); // proves the write genuinely failed, not a no-op mock
      expect(screen.getByTestId("locale")).toHaveTextContent("en");
      expect(screen.getByTestId("cta")).toHaveTextContent("Try it now");
    } finally {
      spy.mockRestore();
    }
  });

  it("a throwing getItem still yields pt-BR on mount, without throwing", async () => {
    const spy = mockStorageMethodToThrow("getItem");

    try {
      render(
        <LocaleProvider>
          <Probe />
        </LocaleProvider>,
      );
      await waitFor(() => expect(screen.getByTestId("locale")).toHaveTextContent("pt-BR"));
      expect(spy).toHaveBeenCalled();
    } finally {
      spy.mockRestore();
    }
  });

  it("a working setItem still persists the switch (the failure path does not disable persistence generally)", async () => {
    render(
      <LocaleProvider>
        <Probe />
      </LocaleProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("locale")).toHaveTextContent("pt-BR"));

    act(() => {
      screen.getByRole("button", { name: "switch to en" }).click();
    });

    expect(readStoredLocale()).toBe("en");
  });

  it("a locale change still notifies every consumer under the provider even after a prior write failure", async () => {
    function Consumer({ testId }: { testId: string }) {
      const { locale } = useLocale();
      return <span data-testid={testId}>{locale}</span>;
    }

    const spy = mockStorageMethodToThrow("setItem");

    try {
      render(
        <LocaleProvider>
          <Consumer testId="x" />
          <Consumer testId="y" />
          <Probe />
        </LocaleProvider>,
      );
      await waitFor(() => expect(screen.getByTestId("x")).toHaveTextContent("pt-BR"));

      act(() => {
        screen.getByRole("button", { name: "switch to en" }).click();
      });

      expect(screen.getByTestId("x")).toHaveTextContent("en");
      expect(screen.getByTestId("y")).toHaveTextContent("en");
    } finally {
      spy.mockRestore();
    }
  });

  /**
   * "Reload/remount after a failed write -> losing the persisted preference
   * is acceptable" (per the fix's design). A same-process unmount/remount
   * within one test does NOT reproduce a real page reload -- `volatileLocale`
   * is ordinary module state, not tied to the component tree, so it would
   * still hold "en" across an in-process remount. A genuine reload clears
   * that JS state along with everything else, so `resetVolatileLocaleForTests`
   * is used here to stand in for that -- the same call the test-isolation
   * `beforeEach` above uses, applied mid-test to model "the process restarted".
   */
  it("a genuine reload after a failed write loses the session locale -- falls back to pt-BR", async () => {
    const spy = mockStorageMethodToThrow("setItem");

    try {
      const { unmount } = render(
        <LocaleProvider>
          <Probe />
        </LocaleProvider>,
      );
      await waitFor(() => expect(screen.getByTestId("locale")).toHaveTextContent("pt-BR"));

      act(() => {
        screen.getByRole("button", { name: "switch to en" }).click();
      });
      expect(screen.getByTestId("locale")).toHaveTextContent("en");
      expect(readStoredLocale()).toBeNull(); // the write genuinely never landed

      unmount();
      resetVolatileLocaleForTests(); // models the JS state a real page reload would clear
    } finally {
      spy.mockRestore();
    }

    render(
      <LocaleProvider>
        <Probe />
      </LocaleProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("locale")).toHaveTextContent("pt-BR"));
  });
});

/**
 * Judgment call, stated explicitly (see LocaleProvider.tsx's module
 * docstring): a `storage` event from another tab changes what
 * `readStoredLocale()` returns, but this tab's own explicit `setLocale`
 * call still wins, because `getSnapshot` checks `volatileLocale` first.
 * Chosen as the simpler defensible behavior over reconciling cross-tab
 * state in this slice.
 */
describe("LocaleProvider -- cross-tab judgment call", () => {
  it("this tab's explicit choice is not overridden by a storage event reporting a different locale", async () => {
    render(
      <LocaleProvider>
        <Probe />
      </LocaleProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("locale")).toHaveTextContent("pt-BR"));

    act(() => {
      screen.getByRole("button", { name: "switch to en" }).click();
    });
    expect(screen.getByTestId("locale")).toHaveTextContent("en");

    // Simulate another tab writing pt-BR and firing the `storage` event this
    // tab's subscription listens for.
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "pt-BR");
    act(() => {
      window.dispatchEvent(new StorageEvent("storage", { key: LOCALE_STORAGE_KEY }));
    });

    expect(screen.getByTestId("locale")).toHaveTextContent("en");
  });

  it("a tab with no explicit choice of its own still picks up another tab's stored value", async () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en");
    render(
      <LocaleProvider>
        <Probe />
      </LocaleProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("locale")).toHaveTextContent("en"));
  });
});

/**
 * `volatileLocale` in LocaleProvider.tsx is module-level state: within one
 * test FILE, it is the same module instance across every `it()`, so it
 * survives exactly like any other unreset global would. This pins that the
 * `beforeEach` reset at the top of this file actually prevents that leakage
 * -- if that reset call were removed, the second test below would start at
 * "en" (left over from the first) instead of the default.
 */
describe("LocaleProvider -- test isolation (module-level session state must not leak between tests)", () => {
  it("test A: switches to English and leaves it switched, with no unmount/cleanup", async () => {
    render(
      <LocaleProvider>
        <Probe />
      </LocaleProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("locale")).toHaveTextContent("pt-BR"));

    act(() => {
      screen.getByRole("button", { name: "switch to en" }).click();
    });
    expect(screen.getByTestId("locale")).toHaveTextContent("en");
  });

  it("test B: starts fresh at pt-BR -- proves the beforeEach reset isolates this test from test A", async () => {
    render(
      <LocaleProvider>
        <Probe />
      </LocaleProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("locale")).toHaveTextContent("pt-BR"));
  });
});
