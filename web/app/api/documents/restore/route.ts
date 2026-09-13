/**
 * T28 / issue #70. Gated proxy for `POST /documents/restore` -- a JSON body
 * (`{text, restore_handle}`), independent of the document surface: a handle
 * carries everything restore needs, so this route requires neither a
 * re-upload nor any governance field. Disabled by default -- see
 * `app/api/documents/export/route.ts`'s docstring for the shared rationale.
 */

import { demoTransparencyDisabledResponse, isDemoTransparencyEnabled } from "@/lib/demoTransparency";
import { proxyJsonPost } from "@/lib/proxy";

export async function POST(request: Request): Promise<Response> {
  if (!isDemoTransparencyEnabled()) {
    return demoTransparencyDisabledResponse();
  }
  return proxyJsonPost("/documents/restore", request);
}
