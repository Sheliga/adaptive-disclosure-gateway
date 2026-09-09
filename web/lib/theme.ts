/**
 * Theme resolution: system preference by default, with an explicit
 * override the user can set, persisted across visits.
 *
 * `docs/advisor-demo.md`: "initial theme follows system preference; explicit
 * user override is supported and persisted". This module owns exactly that
 * logic; `app/globals.css` owns the actual token values for each theme, and
 * a small inline bootstrap script in `app/layout.tsx` calls into the same
 * rules before first paint to avoid a flash of the wrong theme.
 */

export type ThemePreference = "light" | "dark";
export type ThemeSetting = ThemePreference | "system";

const STORAGE_KEY = "adg-theme-preference";

/**
 * Reads the explicit override from `localStorage`, if any. Wrapped in
 * try/catch: `localStorage` throws in some privacy modes/embeds, and this
 * must still render correctly (falling back to "no override") rather than
 * crash the app over a theme preference.
 */
export function readStoredThemePreference(): ThemePreference | null {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return stored === "light" || stored === "dark" ? stored : null;
  } catch {
    return null;
  }
}

/**
 * Persists (or clears, for `null`) the explicit override. Wrapped in
 * try/catch for the same reason as `readStoredThemePreference` -- a storage
 * write failure must never throw out of a theme toggle click.
 */
export function storeThemePreference(preference: ThemePreference | null): void {
  try {
    if (preference === null) {
      window.localStorage.removeItem(STORAGE_KEY);
    } else {
      window.localStorage.setItem(STORAGE_KEY, preference);
    }
  } catch {
    // Best-effort persistence only -- see the module docstring.
  }
}

/** Reads the OS/browser `prefers-color-scheme` media query. */
export function systemPrefersDark(): boolean {
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

/**
 * Resolves the theme that should actually be applied right now: the stored
 * explicit override if one exists, otherwise the system preference.
 */
export function resolveTheme(): ThemePreference {
  const stored = readStoredThemePreference();
  if (stored !== null) {
    return stored;
  }
  return systemPrefersDark() ? "dark" : "light";
}

/**
 * Stamps `data-theme` on the given root element (defaults to
 * `document.documentElement`) to the resolved theme. This is the one DOM
 * write both the inline bootstrap script (`app/layout.tsx`, before first
 * paint) and any later runtime toggle must funnel through, so the two never
 * drift into different logic for "which theme is active right now".
 */
export function applyTheme(theme: ThemePreference, root: HTMLElement = document.documentElement): void {
  root.setAttribute("data-theme", theme);
}

/**
 * Sets an explicit user override, persists it, and applies it immediately.
 * Passing `null` clears the override and reverts to following the system
 * preference.
 */
export function setThemePreference(
  preference: ThemePreference | null,
  root: HTMLElement = document.documentElement,
): void {
  storeThemePreference(preference);
  const resolved = preference ?? (systemPrefersDark() ? "dark" : "light");
  applyTheme(resolved, root);
}

/**
 * The bootstrap script body run inline in `<head>` before first paint (see
 * `app/layout.tsx`). This must be a plain string of vanilla JS -- it runs
 * outside of React/webpack, directly as inline `<script>` content, so it
 * cannot import this module. It deliberately mirrors `resolveTheme`'s logic
 * exactly (stored override else system preference) -- keep the two in sync
 * if either changes.
 */
export const THEME_BOOTSTRAP_SCRIPT = `(function(){try{var s=window.localStorage.getItem(${JSON.stringify(
  STORAGE_KEY,
)});var t=(s==="light"||s==="dark")?s:(window.matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light");document.documentElement.setAttribute("data-theme",t);}catch(e){}})();`;
