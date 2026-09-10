"use client";

/**
 * The one language control in the app shell (T21 fourth slice / #29),
 * rendered next to `ThemeToggle` in `GuidedFlow`'s header -- same visual
 * weight and pattern as that control, so neither dominates the other, and
 * neither dominates the main navigation.
 *
 * A single real `<button>` toggling between the two supported locales, the
 * same shape `ThemeToggle` uses for light/dark: keyboard-operable by
 * construction (a native button responds to Enter/Space with no extra
 * wiring), and its visible text IS its accessible name -- no separate
 * `aria-label` needed.
 *
 * Shows the CURRENT locale's own name from `LOCALE_LABELS` ("Português" /
 * "English") -- a language name is conventionally displayed in that
 * language regardless of the interface's current locale, and deliberately
 * never a flag/emoji: flags denote countries, not languages, and issue #29
 * requires text as the primary/sole indicator here.
 */

import { LOCALE_LABELS } from "@/i18n/locales";
import { useLocale } from "@/i18n/useLocale";

import styles from "./LocaleSwitcher.module.css";

export function LocaleSwitcher() {
  const { locale, setLocale, copy } = useLocale();
  const next = locale === "pt-BR" ? "en-US" : "pt-BR";

  return (
    <button type="button" onClick={() => setLocale(next)} className={styles.toggle}>
      {copy.language.toggleLabel}: {LOCALE_LABELS[locale]}
    </button>
  );
}
