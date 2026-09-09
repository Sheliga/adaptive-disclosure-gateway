import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  applyTheme,
  readStoredThemePreference,
  resolveTheme,
  setThemePreference,
  storeThemePreference,
  THEME_BOOTSTRAP_SCRIPT,
} from "./theme";

function mockMatchMedia(prefersDark: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: query === "(prefers-color-scheme: dark)" ? prefersDark : false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })) as unknown as typeof window.matchMedia;
}

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("resolveTheme — no stored preference", () => {
  it("follows the system preference when it prefers dark", () => {
    mockMatchMedia(true);
    expect(resolveTheme()).toBe("dark");
  });

  it("follows the system preference when it prefers light", () => {
    mockMatchMedia(false);
    expect(resolveTheme()).toBe("light");
  });
});

describe("resolveTheme — explicit stored preference", () => {
  it("uses the stored light override even if the system prefers dark", () => {
    mockMatchMedia(true);
    storeThemePreference("light");
    expect(resolveTheme()).toBe("light");
  });

  it("uses the stored dark override even if the system prefers light", () => {
    mockMatchMedia(false);
    storeThemePreference("dark");
    expect(resolveTheme()).toBe("dark");
  });
});

describe("readStoredThemePreference / storeThemePreference", () => {
  it("round-trips a stored preference", () => {
    storeThemePreference("dark");
    expect(readStoredThemePreference()).toBe("dark");
  });

  it("returns null when nothing was ever stored", () => {
    expect(readStoredThemePreference()).toBeNull();
  });

  it("clears the override when storing null", () => {
    storeThemePreference("dark");
    storeThemePreference(null);
    expect(readStoredThemePreference()).toBeNull();
  });

  it("does not throw and returns null when localStorage.getItem throws", () => {
    const spy = vi.spyOn(window.localStorage, "getItem").mockImplementation(() => {
      throw new Error("storage disabled in this privacy mode");
    });
    expect(() => readStoredThemePreference()).not.toThrow();
    expect(readStoredThemePreference()).toBeNull();
    spy.mockRestore();
  });

  it("does not throw when localStorage.setItem throws", () => {
    const spy = vi.spyOn(window.localStorage, "setItem").mockImplementation(() => {
      throw new Error("storage disabled in this privacy mode");
    });
    expect(() => storeThemePreference("dark")).not.toThrow();
    spy.mockRestore();
  });
});

describe("applyTheme / setThemePreference", () => {
  it("stamps data-theme on the given root", () => {
    const root = document.createElement("html");
    applyTheme("dark", root);
    expect(root.getAttribute("data-theme")).toBe("dark");
  });

  it("setThemePreference persists and applies an explicit override", () => {
    mockMatchMedia(false);
    const root = document.createElement("html");
    setThemePreference("dark", root);
    expect(root.getAttribute("data-theme")).toBe("dark");
    expect(readStoredThemePreference()).toBe("dark");
  });

  it("setThemePreference(null) reverts to the system preference", () => {
    mockMatchMedia(true);
    const root = document.createElement("html");
    setThemePreference("light", root);
    setThemePreference(null, root);
    expect(root.getAttribute("data-theme")).toBe("dark");
    expect(readStoredThemePreference()).toBeNull();
  });
});

describe("THEME_BOOTSTRAP_SCRIPT", () => {
  it("is a non-empty string with no import/require (must run as a raw inline script)", () => {
    expect(typeof THEME_BOOTSTRAP_SCRIPT).toBe("string");
    expect(THEME_BOOTSTRAP_SCRIPT.length).toBeGreaterThan(0);
    expect(THEME_BOOTSTRAP_SCRIPT).not.toMatch(/\bimport\b|\brequire\(/);
  });

  it("stamps data-theme on documentElement when evaluated, honoring a stored override", () => {
    storeThemePreference("dark");
    mockMatchMedia(false);
    // inline in <head>; evaluating it here proves it does what it claims.
    eval(THEME_BOOTSTRAP_SCRIPT);
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("falls back to system preference when evaluated with no stored override", () => {
    mockMatchMedia(true);
    eval(THEME_BOOTSTRAP_SCRIPT);
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("does not throw when localStorage access throws inside the bootstrap script", () => {
    const spy = vi.spyOn(window.localStorage, "getItem").mockImplementation(() => {
      throw new Error("storage disabled");
    });
    mockMatchMedia(false);
    expect(() => eval(THEME_BOOTSTRAP_SCRIPT)).not.toThrow();
    spy.mockRestore();
  });
});
