/**
 * T29 (issue #72) -- the server-side security gate for the demo vault
 * explorer route handler under `app/api/demo/`. Mirrors
 * `lib/demoTransparency.ts`'s structure and posture exactly; see that
 * module's docstring for the full rationale, repeated here only where this
 * gate differs. This module deliberately never spells out the route
 * handler's own upstream path string in prose -- see
 * `tests/test_demo_deployment_config.py::TestWebVaultExplorerIsGated`, which
 * pins that literal path string to appearing only in the route handler
 * itself and in `lib/api.ts`.
 *
 * `isDemoVaultExplorerEnabled` mirrors the Python API's own flag-parsing
 * rule BYTE-IDENTICALLY (`application/settings.py`'s
 * `DEMO_VAULT_EXPLORER_ENV_VAR` / `demo_vault_explorer_enabled`): enabled
 * iff the variable is set AND its stripped value is exactly `"1"`.
 *
 * This module is server-only, must never be imported by client ("use
 * client") code, and the flag must never be exposed as a `NEXT_PUBLIC_*`
 * variable -- see `lib/demoTransparency.ts` for why. The route handler
 * calls this gate BEFORE doing anything else, in particular before ever
 * calling `proxyJsonPost` -- a disabled gate must make zero upstream calls.
 *
 * `demoVaultExplorerDisabledResponse` differs from
 * `demoTransparencyDisabledResponse` in one respect: it also carries
 * `Cache-Control: no-store` / `Pragma: no-cache`, matching the Python API's
 * own posture for this specific route (`api/app.py`'s
 * `_NoStoreOnVaultExplorerASGIMiddleware`) -- a disabled-feature 404 for a
 * surface whose whole purpose is showing reversible local state must be as
 * uncacheable as every other response from this path.
 */

export const DEMO_VAULT_EXPLORER_ENV_VAR = "ADG_ENABLE_DEMO_VAULT_EXPLORER";

export function isDemoVaultExplorerEnabled(
  env: Record<string, string | undefined> = process.env,
): boolean {
  const value = env[DEMO_VAULT_EXPLORER_ENV_VAR];
  return value !== undefined && value.trim() === "1";
}

const DISABLED_BODY = JSON.stringify({ detail: "not found", kind: "DemoVaultExplorerDisabled" });

export function demoVaultExplorerDisabledResponse(): Response {
  return new Response(DISABLED_BODY, {
    status: 404,
    headers: {
      "content-type": "application/json",
      "cache-control": "no-store",
      pragma: "no-cache",
    },
  });
}
