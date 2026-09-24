/**
 * The T27/T28 (issues #69-#70) server-side security gate for the demo
 * transparency surfaces: the export and restore proxy route handlers under
 * `app/api/documents/`, and the read-only feature flag route under
 * `app/api/demo/features/`. This module deliberately never spells out
 * either route handler's own upstream path string in prose -- see
 * `tests/test_demo_deployment_config.py::TestWebExportRestoreIsGated`, which
 * pins those two literal path strings to appearing only in the route
 * handlers themselves and in `lib/api.ts`.
 *
 * `isDemoTransparencyEnabled`'s parsing rule is identical to the other two
 * demo gates (`demoInspection.ts` / `demoVaultExplorer.ts`, and the Python
 * API's own `application/settings.py::demo_inspection_enabled` /
 * `demo_vault_explorer_enabled`): enabled iff the variable is set AND its
 * stripped value is exactly `"1"` -- unset, blank, `"0"`, `"true"`, `"yes"`
 * or anything else is disabled. Disabled is the safe direction, so there is
 * no startup refusal for an unrecognized value. The Python API no longer
 * reads `ADG_ENABLE_DEMO_TRANSPARENCY` at all (issue #103); this gate is now
 * enforced only here, at the web proxy.
 *
 * This module is server-only. It must never be imported by client
 * ("use client") code, and the flag must never be exposed as a
 * `NEXT_PUBLIC_*` variable -- that would bake a build-time snapshot of it
 * into the client bundle, which is exactly wrong for a value that can be
 * (and, per `compose.demo.yaml`, is) supplied at container RUNTIME. Hiding a
 * button client-side is UX only; the actual security boundary is this gate,
 * called by each route handler BEFORE it does anything else (in particular,
 * before ever calling `proxyMultipartPost`/`proxyJsonPost` -- a disabled
 * gate must make zero upstream calls).
 *
 * `demoTransparencyDisabledResponse` is the ONE fixed response every gated
 * route returns when disabled: HTTP 404 (not 403, so the surface reads as
 * "does not exist" rather than confirming a restricted feature merely being
 * off) with a fixed, content-free JSON body -- no hint beyond the `kind`,
 * regardless of which route or request produced it.
 */

export const DEMO_TRANSPARENCY_ENV_VAR = "ADG_ENABLE_DEMO_TRANSPARENCY";

export function isDemoTransparencyEnabled(
  env: Record<string, string | undefined> = process.env,
): boolean {
  const value = env[DEMO_TRANSPARENCY_ENV_VAR];
  return value !== undefined && value.trim() === "1";
}

const DISABLED_BODY = JSON.stringify({ detail: "not found", kind: "DemoTransparencyDisabled" });

export function demoTransparencyDisabledResponse(): Response {
  return new Response(DISABLED_BODY, { status: 404, headers: { "content-type": "application/json" } });
}
