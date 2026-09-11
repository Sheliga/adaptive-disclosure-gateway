import { beforeEach, describe, expect, it, vi } from "vitest";

import { LOCALE_STORAGE_KEY, readStoredLocale, storeLocale } from "./localeStorage";

beforeEach(() => {
  window.localStorage.clear();
});

/**
 * `window.localStorage.getItem = () => { throw ... }` looks like a mock but
 * is NOT one: `Storage` is a legacy platform object whose own [[Set]] (and
 * [[DefineOwnProperty]]) treat a plain assignment on the INSTANCE as writing
 * a storage entry named "getItem"/"setItem", not as replacing the method --
 * the real method lookup still resolves through the prototype. A test using
 * that pattern would pass even if the production `try/catch` were deleted,
 * because the "mocked" method never actually throws. Overriding the method
 * on `Object.getPrototypeOf(window.localStorage)` instead goes through
 * ordinary [[DefineOwnProperty]] and genuinely intercepts the call.
 */
function mockStorageMethodToThrow(method: "getItem" | "setItem") {
  const proto = Object.getPrototypeOf(window.localStorage) as Storage;
  return vi.spyOn(proto, method).mockImplementation(() => {
    throw new Error("blocked");
  });
}

describe("localeStorage -- stable, namespaced key", () => {
  it("uses the adg-locale key, consistent with the sibling adg-theme-preference key", () => {
    expect(LOCALE_STORAGE_KEY).toBe("adg-locale");
  });
});

describe("readStoredLocale", () => {
  it("returns null when nothing has been stored yet", () => {
    expect(readStoredLocale()).toBeNull();
  });

  it("returns the stored locale when it is a known one", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en");
    expect(readStoredLocale()).toBe("en");
  });

  it("falls back to null for an unknown/garbled stored value -- caller decides the default", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "klingon");
    expect(readStoredLocale()).toBeNull();
  });

  /**
   * Regression pin: `en-US` was the first (incorrect) implementation of the
   * English locale code; the slice spec names `en`. A value stored under the
   * old code -- e.g. by a browser that visited before this fix shipped --
   * must be treated as unsupported, exactly like any other unrecognized
   * string, never silently upgraded to `en`.
   */
  it("treats a stored en-US as unsupported, not as an alias for en", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en-US");
    expect(readStoredLocale()).toBeNull();
  });

  it("does not throw when localStorage.getItem throws (privacy mode)", () => {
    const spy = mockStorageMethodToThrow("getItem");
    try {
      expect(() => readStoredLocale()).not.toThrow();
      expect(readStoredLocale()).toBeNull();
      expect(spy).toHaveBeenCalled();
    } finally {
      spy.mockRestore();
    }
  });
});

describe("storeLocale", () => {
  it("persists a supported locale so it can be read back", () => {
    storeLocale("en");
    expect(readStoredLocale()).toBe("en");
  });

  it("overwrites a previously stored locale", () => {
    storeLocale("en");
    storeLocale("pt-BR");
    expect(readStoredLocale()).toBe("pt-BR");
  });

  it("does not throw when localStorage.setItem throws (privacy mode)", () => {
    const spy = mockStorageMethodToThrow("setItem");
    try {
      expect(() => storeLocale("en")).not.toThrow();
      expect(spy).toHaveBeenCalled();
      expect(readStoredLocale()).toBeNull(); // the write genuinely did not happen
    } finally {
      spy.mockRestore();
    }
  });
});
