/**
 * Thin proxy for `GET /examples`. See `lib/proxy.ts` for the shared
 * forwarding contract this and every other route under `app/api/**` must
 * uphold: forward status/body verbatim, never log, fixed 502 on failure.
 */

import { proxyGet } from "@/lib/proxy";

export async function GET(): Promise<Response> {
  return proxyGet("/examples");
}
