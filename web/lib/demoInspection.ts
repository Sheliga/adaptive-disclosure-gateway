/**
 * T32.3 (issue #103) -- the web-tier UX signal for the request-scoped
 * before/after inspection projection (`preview.inspection`), decoupled from
 * `lib/demoTransparency.ts`'s export/restore gate: until #103 that
 * projection rode on `ADG_ENABLE_DEMO_TRANSPARENCY`, the variable that also
 * opens the T28 export/restore re-identification surface, so a deployment
 * could not explain a transformation without also opening restore. Mirrors
 * `lib/demoTransparency.ts`'s structure exactly; see that module's
 * docstring for the fuller rationale, repeated here only where this gate
 * differs.
 *
 * `isDemoInspectionEnabled` mirrors the Python API's own flag-parsing rule
 * BYTE-IDENTICALLY (`application/settings.py`'s `DEMO_INSPECTION_ENV_VAR` /
 * `demo_inspection_enabled`): enabled iff the variable is set AND its
 * stripped value is exactly `"1"` -- unset, blank, `"0"`, `"true"`, `"yes"`
 * or anything else is disabled. Disabled is the safe direction, so there is
 * no startup refusal for an unrecognized value.
 *
 * This module is server-only. It must never be imported by client ("use
 * client") code, and the flag must never be exposed as a `NEXT_PUBLIC_*`
 * variable -- that would bake a build-time snapshot of it into the client
 * bundle, which is exactly wrong for a value that can be supplied at
 * container RUNTIME.
 *
 * Unlike `demoTransparency.ts`/`demoVaultExplorer.ts`, this module exports
 * no disabled-response helper: no web route is gated by this flag. The
 * inspection data itself arrives inside `POST /disclosure/preview`'s own
 * response body, gated by the Python API's own `demo_inspection_enabled`
 * gate -- that is the actual security boundary. This module (and the
 * `demo_inspection_enabled` field `app/api/demo/features/route.ts`
 * reports from it) is a UX signal only, telling the client whether to
 * bother rendering an inspection affordance; it decides nothing
 * security-relevant, and a stale or wrong answer here can at most hide or
 * show a button, never change what the API actually returns.
 */

export const DEMO_INSPECTION_ENV_VAR = "ADG_ENABLE_DEMO_INSPECTION";

export function isDemoInspectionEnabled(
  env: Record<string, string | undefined> = process.env,
): boolean {
  const value = env[DEMO_INSPECTION_ENV_VAR];
  return value !== undefined && value.trim() === "1";
}
