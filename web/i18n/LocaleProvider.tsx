"use client";

/**
 * Owns the actual locale STATE (as opposed to `LocaleContext.tsx`, which
 * only defines the shape/default). Wraps the app shell (`GuidedFlow`, which
 * `app/page.tsx`'s own docstring calls "the whole app for this slice") so
 * every screen underneath shares one locale via `useLocale`/`useCopy`,
 * never a component-local copy of it.
 *
 * --- Hydration mismatch, handled deliberately (T21 fourth slice) ---
 *
 * The app is server-rendered. `localStorage` is client-only, and the server
 * has no concept of "the stored locale" at all. If the locale state here
 * were computed by reading storage directly during render (`useState(() =>
 * readStoredLocale() ?? DEFAULT_LOCALE)`), the very first CLIENT render
 * would differ from the server-rendered HTML whenever a locale was already
 * stored -- a hydration mismatch across the entire text of the app, not a
 * single attribute like `lib/theme.ts`'s `data-theme` (which sidesteps the
 * problem with a `suppressHydrationWarning`-guarded lazy initializer, since
 * it is one DOM attribute rather than the text content of every screen --
 * see `ThemeToggle.tsx`'s docstring). Text content is not something React
 * lets you opt out of comparing, so that approach cannot simply be copied
 * here.
 *
 * `useSyncExternalStore` is the tool React itself provides for exactly this
 * class of problem -- reading a value that lives OUTSIDE React (here,
 * `localStorage`) that can differ between server and client. Its third
 * argument, `getServerSnapshot`, is used for the server render AND for
 * React's first client render (the one hydration compares against), so it
 * -- not `getSnapshot` -- decides what appears before storage is ever
 * consulted. `getServerSnapshot` here is `initialLocale`, a plain function
 * that always returns `DEFAULT_LOCALE` and never touches storage (provable
 * in isolation -- see `LocaleProvider.test.tsx`), matching the
 * server-rendered pt-BR markup exactly. React then re-reads `getSnapshot`
 * immediately after hydration/mount and re-renders with the real stored
 * value -- the same "apply real state after mount" shape as a manual
 * mount effect, but without a synchronous `setState` inside a `useEffect`
 * body (flagged by `react-hooks/set-state-in-effect`) and without a second,
 * hand-rolled state variable to keep in sync with storage.
 *
 * Writing a new locale (`setLocale`) still funnels through `storeLocale`,
 * then calls `notify()` on this module's own listener set -- `storage`
 * events only fire in OTHER tabs/windows, never the tab that made the
 * write, so this in-module pub/sub is what makes the CURRENT tab's click
 * update its own `useSyncExternalStore` snapshot.
 *
 * --- Session state vs. persistence (blocker fix, T21 fourth slice) ---
 *
 * `storeLocale` is best-effort: `localStorage.setItem` can throw (privacy
 * mode, an embed, a browser storage policy). Before this fix, `getSnapshot`
 * had NO other source of truth than storage -- `readStoredLocale() ??
 * DEFAULT_LOCALE` -- so a throwing write left `setLocale` having written
 * nothing, `notify()` firing, and every consumer re-reading the SAME old
 * value from storage. The click did not crash, but it also did not do
 * anything: the language silently failed to change for the rest of the
 * session.
 *
 * `volatileLocale` is the fix: an in-memory session value that is the
 * PRIMARY source for `getSnapshot`, with storage only a secondary source
 * consulted when nothing has been explicitly chosen this session yet.
 * `setLocale` sets it unconditionally, before attempting to persist --
 * so a persistence failure can never prevent the current session from
 * changing language, which is the actual product requirement (persistence
 * is a nice-to-have across visits, not a precondition for the UI to work
 * within one). `volatileLocale` starts `null`, so the very first client
 * snapshot -- the one hydration compares against -- is unaffected; it is
 * consulted only after at least one `setLocale` call in this session.
 *
 * Judgment call: a `storage` event from another tab changes what
 * `readStoredLocale()` returns, but `volatileLocale` set by an explicit
 * choice IN THIS tab still wins over it, because `getSnapshot` checks
 * `volatileLocale` first. This is a deliberate, simple choice over
 * reconciling cross-tab state in this slice: this tab's own explicit
 * choice stays authoritative for this tab's session, and a fresh tab (no
 * `volatileLocale` of its own yet) still picks up the other tab's write
 * through storage, same as before this fix.
 *
 * `resetVolatileLocaleForTests` exists ONLY for test isolation: this is
 * module-level (not React) state, so it survives across `it()` blocks
 * within the same test file/module instance -- a test that switches to
 * English would otherwise leak that choice into the next test that expects
 * to start at the default. Production code never calls it.
 */

import { useCallback, useEffect, useMemo, useSyncExternalStore } from "react";
import type { ReactNode } from "react";

import { resolveCopy } from "@/lib/copy";

import { LocaleContext } from "./LocaleContext";
import { DEFAULT_LOCALE, type Locale } from "./locales";
import { readStoredLocale, storeLocale } from "./localeStorage";

const listeners = new Set<() => void>();

/**
 * This session's explicit locale choice, independent of whether it could be
 * persisted. `null` means "nothing chosen yet this session" -- fall through
 * to storage, then to the default. See the module docstring's "Session
 * state vs. persistence" section for why this exists.
 */
let volatileLocale: Locale | null = null;

function notify(): void {
  for (const listener of listeners) {
    listener();
  }
}

function subscribe(onStoreChange: () => void): () => void {
  listeners.add(onStoreChange);
  window.addEventListener("storage", onStoreChange);
  return () => {
    listeners.delete(onStoreChange);
    window.removeEventListener("storage", onStoreChange);
  };
}

function getSnapshot(): Locale {
  return volatileLocale ?? readStoredLocale() ?? DEFAULT_LOCALE;
}

/**
 * Test-only escape hatch: clears the in-memory session locale so the next
 * test in the same file does not inherit a previous test's switch. Never
 * called from production code -- see the module docstring.
 */
export function resetVolatileLocaleForTests(): void {
  volatileLocale = null;
}

/**
 * Exported purely so `LocaleProvider.test.tsx` can pin, directly and in
 * isolation, that this never reads storage -- the property the whole
 * hydration-safety argument above rests on. Also `useSyncExternalStore`'s
 * `getServerSnapshot`.
 */
export function initialLocale(): Locale {
  return DEFAULT_LOCALE;
}

export function LocaleProvider({ children }: { children: ReactNode }) {
  const locale = useSyncExternalStore(subscribe, getSnapshot, initialLocale);

  useEffect(() => {
    // A locale is a page-language fact, not just a copy-table choice --
    // keeping `<html lang>` in sync benefits assistive technology. Guarded
    // the same way the theme bootstrap script guards `data-theme`: applied
    // after mount, never assumed to match the server-rendered attribute.
    // This is a genuine "synchronize an external system" effect (writing to
    // the DOM), not a `setState` call, so it does not trip the same lint
    // rule the old mount-effect design did.
    document.documentElement.lang = locale;
  }, [locale]);

  const setLocale = useCallback((next: Locale) => {
    // Session state first: this is what makes the switch work even when
    // `storeLocale` below fails (see module docstring). `storeLocale` is
    // still attempted for cross-visit persistence, but its outcome no
    // longer gates whether THIS session's locale actually changes.
    volatileLocale = next;
    storeLocale(next);
    notify();
  }, []);

  const value = useMemo(
    () => ({ locale, setLocale, copy: resolveCopy(locale) }),
    [locale, setLocale],
  );

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}
