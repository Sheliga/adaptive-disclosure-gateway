import { describe, expect, it } from "vitest";

import { DEFAULT_LOCALE, isSupportedLocale, SUPPORTED_LOCALES } from "./locales";

describe("locales -- the closed set of locales the app admits", () => {
  it("supports exactly pt-BR and en, no arbitrary strings", () => {
    expect(SUPPORTED_LOCALES).toEqual(["pt-BR", "en"]);
  });

  it("defaults to pt-BR -- the product default, not browser auto-detection", () => {
    expect(DEFAULT_LOCALE).toBe("pt-BR");
    expect(SUPPORTED_LOCALES).toContain(DEFAULT_LOCALE);
  });

  it("recognizes every supported locale", () => {
    expect(isSupportedLocale("pt-BR")).toBe(true);
    expect(isSupportedLocale("en")).toBe(true);
  });

  it("rejects anything that is not one of the two supported locales", () => {
    expect(isSupportedLocale("fr-FR")).toBe(false);
    expect(isSupportedLocale("pt-br")).toBe(false); // case-sensitive, no fuzzy match
    expect(isSupportedLocale("")).toBe(false);
    expect(isSupportedLocale(undefined)).toBe(false);
    expect(isSupportedLocale(null)).toBe(false);
    expect(isSupportedLocale(42)).toBe(false);
  });

  /**
   * Regression pin for the exact defect this PR fixes: the slice spec named
   * `en`, the first implementation shipped `en-US`. `en-US` must never come
   * back as an accepted alias -- a stored `"en-US"` (from before this fix,
   * or from any other source) is an UNSUPPORTED value now, not a synonym for
   * `en`, so it falls back to `DEFAULT_LOCALE` like any other unknown value.
   */
  it("no longer accepts en-US -- it is not an alias for en", () => {
    expect(isSupportedLocale("en-US")).toBe(false);
    expect(SUPPORTED_LOCALES).not.toContain("en-US");
  });
});
