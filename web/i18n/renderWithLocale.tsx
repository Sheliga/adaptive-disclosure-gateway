/**
 * Test-only helper shared by the per-screen "switches to English" tests
 * (T21 fourth slice / #29). Not imported by any production module.
 *
 * Presets `localStorage` with a locale BEFORE rendering, then wraps the
 * given UI in a real `LocaleProvider` and waits for its mount effect to
 * apply the stored preference -- the same path a real remount takes (see
 * `LocaleProvider.tsx`'s docstring on why the initial render always starts
 * at `DEFAULT_LOCALE` and only an effect applies a stored value). This is
 * more honest than passing a locale as a prop: it exercises the exact
 * storage-read code path each screen relies on, not a shortcut around it.
 */

import { render, waitFor, type RenderResult } from "@testing-library/react";
import type { ReactElement } from "react";
import { expect } from "vitest";

import { LocaleProvider } from "./LocaleProvider";
import type { Locale } from "./locales";
import { LOCALE_STORAGE_KEY } from "./localeStorage";

export async function renderWithLocale(ui: ReactElement, locale: Locale): Promise<RenderResult> {
  window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
  const result = render(<LocaleProvider>{ui}</LocaleProvider>);
  // Any string that only exists in one locale's copy table would do here;
  // waiting on the document's own lang attribute keeps this helper generic
  // across every screen rather than depending on one screen's specific text.
  await waitFor(() => expect(document.documentElement.lang).toBe(locale));
  return result;
}
