/**
 * Thin proxy for `GET /ready`. See `lib/proxy.ts` for the shared forwarding
 * contract this and every other route under `app/api/**` must uphold:
 * forward status/body verbatim, never log, fixed 502 on failure.
 *
 * Distinct from `app/api/health/route.ts`: the upstream `/ready` returns 503
 * (not 200) when the API is not ready, and this route forwards that status
 * unchanged -- exactly the dumb-pipe contract every other route here already
 * follows, so a compose/orchestrator healthcheck against this route tracks
 * the real API's readiness.
 */

import { proxyGet } from "@/lib/proxy";

export async function GET(): Promise<Response> {
  return proxyGet("/ready");
}
