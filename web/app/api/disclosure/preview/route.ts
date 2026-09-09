/**
 * Thin proxy for `POST /disclosure/preview`. Forwards the request body
 * unchanged and mirrors the upstream status/body unchanged -- see
 * `lib/proxy.ts` for the shared no-reshaping, no-retry, no-logging
 * contract every route under `app/api/**` upholds.
 */

import { proxyJsonPost } from "@/lib/proxy";

export async function POST(request: Request): Promise<Response> {
  return proxyJsonPost("/disclosure/preview", request);
}
