/**
 * T27/T28 (issues #69-#70) -- a web-only, purely presentational endpoint:
 * whether the export/restore UI (and, by extension, the fact that the
 * inspector may be populated) should render at all, computed from the SAME
 * `ADG_ENABLE_DEMO_TRANSPARENCY` gate `lib/demoTransparency.ts` enforces on
 * the export/restore routes. It never returns anything beyond that one
 * boolean -- no secret, no config value, no upstream call at all.
 *
 * T29 / issue #72 adds `demo_vault_explorer_enabled` alongside it, computed
 * the same way from `lib/demoVaultExplorer.ts`'s independent
 * `ADG_ENABLE_DEMO_VAULT_EXPLORER` gate -- the two flags are unrelated
 * deployment toggles, so this endpoint never derives one from the other.
 *
 * `dynamic = "force-dynamic"` is required, not cosmetic: without it, `next
 * build` may statically prerender this route once at build time and bake
 * whatever these flags happened to be set to during the image build into
 * every response the running container ever serves -- exactly the class of
 * bug `docs/*` warns about for `ADG_API_BASE_URL`, and this endpoint has the
 * exact same "must be evaluated at request time" requirement. Even though
 * this route reads `process.env` (which Next.js treats as dynamic in most
 * configurations), the config is declared explicitly rather than relied
 * upon implicitly, so a future Next.js/config change cannot silently
 * reintroduce static prerendering here.
 */

import { isDemoTransparencyEnabled } from "@/lib/demoTransparency";
import { isDemoVaultExplorerEnabled } from "@/lib/demoVaultExplorer";

export const dynamic = "force-dynamic";

export async function GET(): Promise<Response> {
  return new Response(
    JSON.stringify({
      demo_transparency_enabled: isDemoTransparencyEnabled(),
      demo_vault_explorer_enabled: isDemoVaultExplorerEnabled(),
    }),
    {
      status: 200,
      headers: { "content-type": "application/json" },
    },
  );
}
