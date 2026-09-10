import { beforeEach, describe, expect, it } from "vitest";

import { LOCALE_STORAGE_KEY, readStoredLocale, storeLocale } from "./localeStorage";

beforeEach(() => {
  window.localStorage.clear();
});

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
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en-US");
    expect(readStoredLocale()).toBe("en-US");
  });

  it("falls back to null for an unknown/garbled stored value -- caller decides the default", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "klingon");
    expect(readStoredLocale()).toBeNull();
  });

  it("does not throw when localStorage.getItem throws (privacy mode)", () => {
    const original = window.localStorage.getItem;
    window.localStorage.getItem = () => {
      throw new Error("blocked");
    };
    expect(() => readStoredLocale()).not.toThrow();
    expect(readStoredLocale()).toBeNull();
    window.localStorage.getItem = original;
  });
});

describe("storeLocale", () => {
  it("persists a supported locale so it can be read back", () => {
    storeLocale("en-US");
    expect(readStoredLocale()).toBe("en-US");
  });

  it("overwrites a previously stored locale", () => {
    storeLocale("en-US");
    storeLocale("pt-BR");
    expect(readStoredLocale()).toBe("pt-BR");
  });

  it("does not throw when localStorage.setItem throws (privacy mode)", () => {
    const original = window.localStorage.setItem;
    window.localStorage.setItem = () => {
      throw new Error("blocked");
    };
    expect(() => storeLocale("en-US")).not.toThrow();
    window.localStorage.setItem = original;
  });
});
