/**
 * The one way a component reads/changes the current locale or its resolved
 * copy table. Never `localStorage` directly, never a component-local
 * `useState<Locale>` -- both would duplicate the single source of truth
 * `LocaleProvider` already owns (see its docstring).
 */

import { useContext } from "react";

import type { AppCopy } from "@/lib/copy";

import { LocaleContext, type LocaleContextValue } from "./LocaleContext";

export function useLocale(): LocaleContextValue {
  return useContext(LocaleContext);
}

/** Convenience for the common case: a component that only needs the resolved copy table. */
export function useCopy(): AppCopy {
  return useContext(LocaleContext).copy;
}
