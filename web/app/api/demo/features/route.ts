/**
 * T27/T28 (issues #69-#70) -- a web-only, purely presentational endpoint:
 * whether the export/restore UI (and, by extension, the fact that the
 * inspector may be populated) should render at all, computed from the SAME
 * `ADG_ENABLE_DEMO_TRANSPARENCY` gate `lib/demoTransparency.ts` enforces on
 * the export/restore routes. It never returns anything beyond that one
 * boolean -- no secret, no config value, no upstream call at all.
 *
 * `dynamic = "force-dynamic"` is required, not cosmetic: without it, `next
 * build` may statically prerender this route once at build time and bake
 * whatever `ADG_ENABLE_DEMO_TRANSPARENCY` happened to be set to during the
 * image build into every response the running container ever serves --
 * exactly the class of bug `docs/*` warns about for `ADG_API_BASE_URL`, and
 * this endpoint has the exact same "must be evaluated at request time"
 * requirement. Even though this route reads `process.env` (which Next.js
 * treats as dynamic in most configurations), the config is declared
 * explicitly rather than relied upon implicitly, so a future Next.js/config
 * change cannot silently reintroduce static prerendering here.
 */

import { isDemoTransparencyEnabled } from "@/lib/demoTransparency";

export const dynamic = "force-dynamic";

export async function GET(): Promise<Response> {
  return new Response(JSON.stringify({ demo_transparency_enabled: isDemoTransparencyEnabled() }), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}
