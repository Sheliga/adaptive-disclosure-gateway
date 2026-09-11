/**
 * Persists the user's explicit locale choice across visits/remounts.
 *
 * Mirrors `lib/theme.ts`'s `readStoredThemePreference`/`storeThemePreference`
 * on purpose -- same storage shape, same fail-soft posture -- so the two
 * sibling preferences (theme, locale) behave identically to anyone reading
 * either module. `adg-locale` sits next to the existing `adg-theme-preference`
 * key: same `adg-` namespace, same flat string value, easy to tell apart in
 * devtools storage inspection.
 *
 * Every read and write is wrapped in try/catch: `localStorage` throws in
 * some privacy modes/embeds, and a preference must never crash the app --
 * worst case, the locale silently reverts to `DEFAULT_LOCALE` every visit.
 */

import { isSupportedLocale, type Locale } from "./locales";

export const LOCALE_STORAGE_KEY = "adg-locale";

/**
 * Reads the stored locale, if any. Returns `null` for "nothing stored",
 * "a value that is not one of `SUPPORTED_LOCALES`" and "the read failed" --
 * all three mean the same thing to a caller: fall back to the default
 * rather than trust this value.
 */
export function readStoredLocale(): Locale | null {
  try {
    const stored = window.localStorage.getItem(LOCALE_STORAGE_KEY);
    return isSupportedLocale(stored) ? stored : null;
  } catch {
    return null;
  }
}

/** Persists an explicit locale choice. Best-effort only -- see module docstring. */
export function storeLocale(locale: Locale): void {
  try {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
  } catch {
    // Best-effort persistence only.
  }
}
