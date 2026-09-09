import type { Metadata } from "next";

import { THEME_BOOTSTRAP_SCRIPT } from "@/lib/theme";

import "./globals.css";

export const metadata: Metadata = {
  title: "Gateway de Divulgação Adaptativa",
  description:
    "Demonstração guiada do Adaptive Disclosure Gateway: veja o que permanece local, o que é enviado a um provedor externo e o que é reconstruído localmente.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
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
