/**
 * The closed set of locales this UI admits (T21 / issue #29's fourth slice:
 * pt-BR / English localization).
 *
 * Deliberately a small explicit union, not an arbitrary string -- every
 * place a locale flows through the app (storage, context, the switcher)
 * types against `Locale`, so a typo or an unsupported value is a compile
 * error at the call site, and anything arriving from the outside world
 * (`localStorage`, in particular) must pass through `isSupportedLocale`
 * before it is trusted as one.
 *
 * pt-BR is the product default (`docs/advisor-demo.md`, CLAUDE.md): a first
 * visit, or any stored value this module does not recognize, resolves to
 * `DEFAULT_LOCALE` -- never to a browser/OS language guess.
 */

export const SUPPORTED_LOCALES = ["pt-BR", "en"] as const;

export type Locale = (typeof SUPPORTED_LOCALES)[number];

export const DEFAULT_LOCALE: Locale = "pt-BR";

/**
 * Each language's own name, in that language -- "Português", "English".
 * Deliberately NOT part of `lib/copy.ts`: a language's name is conventionally
 * shown in itself regardless of the interface's current locale (the reader
 * looking for "Português" should find that word whether the UI is currently
 * in English or Portuguese), so this table does not vary with `AppCopy`.
 * Never a flag/emoji -- flags denote countries, not languages.
 */
export const LOCALE_LABELS: Record<Locale, string> = {
  "pt-BR": "Português",
  en: "English",
};

/**
 * Type guard for anything that might name a locale: a raw `localStorage`
 * read, in practice. Unknown/unparseable input -- including case variants,
 * `null`, `undefined` and non-string values -- fails closed to `false`
 * rather than being coerced or fuzzy-matched.
 */
export function isSupportedLocale(value: unknown): value is Locale {
  return typeof value === "string" && (SUPPORTED_LOCALES as readonly string[]).includes(value);
}
