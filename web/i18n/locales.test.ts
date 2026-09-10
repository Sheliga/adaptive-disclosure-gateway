import { describe, expect, it } from "vitest";

import { DEFAULT_LOCALE, isSupportedLocale, SUPPORTED_LOCALES } from "./locales";

describe("locales -- the closed set of locales the app admits", () => {
  it("supports exactly pt-BR and en-US, no arbitrary strings", () => {
    expect(SUPPORTED_LOCALES).toEqual(["pt-BR", "en-US"]);
  });

  it("defaults to pt-BR -- the product default, not browser auto-detection", () => {
    expect(DEFAULT_LOCALE).toBe("pt-BR");
    expect(SUPPORTED_LOCALES).toContain(DEFAULT_LOCALE);
  });

  it("recognizes every supported locale", () => {
    expect(isSupportedLocale("pt-BR")).toBe(true);
    expect(isSupportedLocale("en-US")).toBe(true);
  });

  it("rejects anything that is not one of the two supported locales", () => {
    expect(isSupportedLocale("fr-FR")).toBe(false);
    expect(isSupportedLocale("pt-br")).toBe(false); // case-sensitive, no fuzzy match
    expect(isSupportedLocale("")).toBe(false);
    expect(isSupportedLocale(undefined)).toBe(false);
    expect(isSupportedLocale(null)).toBe(false);
    expect(isSupportedLocale(42)).toBe(false);
  });
});
