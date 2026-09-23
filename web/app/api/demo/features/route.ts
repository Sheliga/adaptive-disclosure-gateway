/**
 * A web-only, purely presentational endpoint reporting three independent
 * demo capabilities, each gated server-side by its own environment
 * variable and each parsed by the same fail-closed rule (enabled iff the
 * variable is set and its trimmed value is exactly "1"):
 *
 * - `demo_inspection_enabled` (T32.3 / issue #103) -- whether the
 *   request-scoped before/after inspection projection
 *   (`PreviewResponse.inspection`) may be populated, from
 *   `lib/demoInspection.ts`'s `ADG_ENABLE_DEMO_INSPECTION` gate.
 * - `demo_transparency_enabled` (T27/T28, issues #69-#70) -- whether the
 *   export/restore UI should render, from `lib/demoTransparency.ts`'s
 *   `ADG_ENABLE_DEMO_TRANSPARENCY` gate.
 * - `demo_vault_explorer_enabled` (T29 / issue #72) -- whether the vault
 *   explorer UI should render, from `lib/demoVaultExplorer.ts`'s
 *   `ADG_ENABLE_DEMO_VAULT_EXPLORER` gate.
 *
 * None of the three is derived from another, in either direction -- they
 * are unrelated deployment toggles, and a public deployment may enable any
 * one of them without the other two. This endpoint never returns anything
 * beyond these three booleans -- no secret, no config value, no upstream
 * call at all. It is a UX signal only: each capability's actual security
 * boundary is enforced independently, server-side, where that capability is
 * used, regardless of what this endpoint last reported.
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

import { isDemoInspectionEnabled } from "@/lib/demoInspection";
import { isDemoTransparencyEnabled } from "@/lib/demoTransparency";
import { isDemoVaultExplorerEnabled } from "@/lib/demoVaultExplorer";

export const dynamic = "force-dynamic";

export async function GET(): Promise<Response> {
  return new Response(
    JSON.stringify({
      demo_inspection_enabled: isDemoInspectionEnabled(),
      demo_transparency_enabled: isDemoTransparencyEnabled(),
      demo_vault_explorer_enabled: isDemoVaultExplorerEnabled(),
    }),
    {
      status: 200,
      headers: { "content-type": "application/json" },
    },
  );
}
