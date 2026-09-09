"use client";

/**
 * The one theme control in the app shell (`docs/advisor-demo.md`: "Light
 * and dark themes ... both required from the MVP"). All logic (resolution,
 * persistence, applying `data-theme`) lives in `lib/theme.ts` -- this
 * component is a thin presentational wrapper that reads the current theme
 * once and flips it on click.
 *
 * The initial value comes from a lazy `useState` initializer guarded on
 * `typeof window` (server render has none; `lib/theme.ts`'s functions touch
 * `window`/`localStorage`) rather than a `useEffect`, so the real theme is
 * known on the very first client render instead of one render late. That
 * client render intentionally differs from the server-rendered fallback --
 * exactly like `app/layout.tsx`'s inline bootstrap script already does for
 * `data-theme` before first paint -- so the button's label carries
 * `suppressHydrationWarning`, React's sanctioned escape hatch for content
 * that deliberately differs between server and client.
 */

import { useState } from "react";

import { copy } from "@/lib/copy";
import { resolveTheme, setThemePreference, type ThemePreference } from "@/lib/theme";

import styles from "./ThemeToggle.module.css";

function initialTheme(): ThemePreference {
  return typeof window === "undefined" ? "light" : resolveTheme();
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<ThemePreference>(initialTheme);

  function handleClick() {
    const next: ThemePreference = theme === "dark" ? "light" : "dark";
    setThemePreference(next);
    setTheme(next);
  }

  const themeLabel = theme === "dark" ? copy.theme.dark : copy.theme.light;

  return (
    <button
      type="button"
      onClick={handleClick}
      aria-pressed={theme === "dark"}
      className={styles.toggle}
      suppressHydrationWarning
    >
      {copy.theme.toggleLabel}: {themeLabel}
    </button>
  );
}
