/**
 * The locale context itself, split from `LocaleProvider.tsx` so a consumer
 * can import just the context shape/default without pulling in the
 * provider's mount-effect/storage wiring.
 *
 * The DEFAULT context value (used by any component rendered without a
 * `<LocaleProvider>` ancestor -- every existing screen unit test does this)
 * is a fully working pt-BR value, not `undefined`. This is deliberate: it
 * means `useLocale()`/`useCopy()` never need a "no provider" error path,
 * and every screen test written before this slice keeps working unchanged,
 * because "no provider" and "provider defaulted to pt-BR" render
 * identically. `setLocale` on the default value is a no-op -- there is no
 * state for it to update outside a real provider.
 */

import { createContext } from "react";

import { type AppCopy, resolveCopy } from "@/lib/copy";

import { DEFAULT_LOCALE, type Locale } from "./locales";

export interface LocaleContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  copy: AppCopy;
}

export const LocaleContext = createContext<LocaleContextValue>({
  locale: DEFAULT_LOCALE,
  setLocale: () => {},
  copy: resolveCopy(DEFAULT_LOCALE),
});
