import type { Metadata } from "next";
import type { ReactNode } from "react";

import { THEME_BOOTSTRAP_SCRIPT } from "@/lib/theme";

import "./globals.css";

export const metadata: Metadata = {
  title: "Gateway de Divulgação Adaptativa",
  description:
    "Demonstração guiada do Adaptive Disclosure Gateway: veja o que permanece local, o que é enviado a um provedor externo e o que é reconstruído localmente.",
};

/**
 * Props are declared explicitly rather than using Next's generated global
 * `LayoutProps<"/">`. That global lives in `.next/types`, which only exists
 * after a build or an explicit `next typegen`, so depending on it makes
 * `tsc --noEmit` fail on any clean checkout that has not built yet --
 * exactly what happened on CI, where typecheck runs before build. The root
 * layout has no dynamic route segments, so `children` is the whole of what
 * the generated type would have provided anyway.
 */
interface RootLayoutProps {
  children: ReactNode;
}

export default function RootLayout({ children }: RootLayoutProps) {
  return (
    <html lang="pt-BR">
      <head>
        {/*
          Sets `data-theme` before first paint, following the same rule
          `lib/theme.ts`'s `resolveTheme` implements at runtime (stored
          override, else system preference) -- this avoids a flash of the
          wrong theme between HTML parse and React hydration. Kept as a
          plain string constant (not inline JS authored here) so the
          bootstrap logic has exactly one source of truth; see
          `lib/theme.ts`'s own docstring for why it cannot import that
          module directly.
        */}
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOTSTRAP_SCRIPT }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
