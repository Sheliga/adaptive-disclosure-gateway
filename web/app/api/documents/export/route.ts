/**
 * T28 / issue #70. Gated proxy for `POST /documents/export` -- the same
 * multipart shape as `documents/preview` (file, task, document_type,
 * [analysis_mode], [strategy]; no confirmation token). Disabled by default:
 * the demo transparency surfaces are an opt-in layered on top of the demo,
 * never a precondition for it (`docs/adr/0002-deferred-restore-handles.md`).
 *
 * The gate check happens BEFORE anything else, including before the
 * incoming request's content-type is even inspected -- a disabled flag must
 * make zero upstream calls, never even a malformed-request round trip.
 */

import { demoTransparencyDisabledResponse, isDemoTransparencyEnabled } from "@/lib/demoTransparency";
import { proxyMultipartPost } from "@/lib/proxy";

export async function POST(request: Request): Promise<Response> {
  if (!isDemoTransparencyEnabled()) {
    return demoTransparencyDisabledResponse();
  }
  return proxyMultipartPost("/documents/export", request);
}
