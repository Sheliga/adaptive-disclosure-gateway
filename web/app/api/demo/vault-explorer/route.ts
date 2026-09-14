/**
 * T29 / issue #72. Gated proxy for `POST /demo/vault-explorer` -- a JSON
 * body (`{token}`), independent of the document/disclosure surfaces: a
 * sealed reference a prior preview issued carries everything the vault
 * explorer needs. Disabled by default -- see `lib/demoVaultExplorer.ts`'s
 * docstring for the gate this route checks before anything else.
 *
 * `dynamic = "force-dynamic"` is required, not cosmetic -- same rationale as
 * `app/api/demo/features/route.ts`: without it, `next build` may statically
 * prerender this route and bake whatever `ADG_ENABLE_DEMO_VAULT_EXPLORER`
 * happened to be set to during the image build into every response the
 * running container ever serves.
 *
 * Every response this route returns -- disabled or forwarded -- carries
 * `Cache-Control: no-store` / `Pragma: no-cache`, mirroring the Python API's
 * own posture for this path (`api/app.py`'s
 * `_NoStoreOnVaultExplorerASGIMiddleware`). The disabled response already
 * carries them (`demoVaultExplorerDisabledResponse`); the forwarded response
 * is rebuilt with a fresh header set on top of whatever the upstream sent,
 * since `proxyJsonPost` (via `lib/proxy.ts`) forwards the upstream's
 * `content-type` only and does not itself add these.
 */

import { demoVaultExplorerDisabledResponse, isDemoVaultExplorerEnabled } from "@/lib/demoVaultExplorer";
import { proxyJsonPost } from "@/lib/proxy";

export const dynamic = "force-dynamic";

async function withNoStore(response: Response): Promise<Response> {
  const headers = new Headers(response.headers);
  headers.set("cache-control", "no-store");
  headers.set("pragma", "no-cache");
  const bodyText = await response.text();
  return new Response(bodyText, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

export async function POST(request: Request): Promise<Response> {
  if (!isDemoVaultExplorerEnabled()) {
    return demoVaultExplorerDisabledResponse();
  }
  const upstreamResponse = await proxyJsonPost("/demo/vault-explorer", request);
  return withNoStore(upstreamResponse);
}
