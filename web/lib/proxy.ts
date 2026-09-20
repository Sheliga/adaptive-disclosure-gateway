/**
 * The forwarding core behind every `web/app/api/**` route handler.
 *
 * `docs/advisor-demo.md`'s topology is `browser -> web container -> API
 * container`: the browser never talks to the Python API directly (keeps
 * credentials/the API off the public origin, avoids CORS entirely). Every
 * route handler in `app/api/**` must therefore be a DUMB pipe over this
 * module: forward the request body unchanged, forward the upstream status
 * code unchanged, forward the upstream JSON body unchanged. No retries, no
 * reshaping, no defaults, no validation of its own -- the Python API and
 * `application/wire.py` already own every one of those concerns.
 *
 * No-leak posture for this specific boundary (CLAUDE.md's invariant applied
 * to a network hop instead of an exception): this module must NEVER log
 * the request body or the upstream response body, since both can carry the
 * user's uploaded document text. It also never logs at all today -- no
 * `console.*` call exists in this file -- specifically so a future edit
 * cannot casually add a `console.log(body)` debug line without first
 * deleting a comment that says not to.
 *
 * When the upstream is unreachable (`fetch` itself throws -- DNS failure,
 * connection refused, timeout, ...), this returns a fixed, generic 502 body
 * containing no exception text, mirroring the Python adapter's own
 * catch-all posture in `api/app.py`'s `_handle_unexpected_exception`.
 */

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";

function apiBaseUrl(): string {
  return process.env.ADG_API_BASE_URL || DEFAULT_API_BASE_URL;
}

/**
 * Mirrors the shape of `application/wire.py`'s `ErrorResponse` so a client
 * that already knows how to render `{detail, kind}` handles this the same
 * way it handles any other upstream error -- it is just never able to
 * distinguish "the Python app returned this" from "Next.js could not reach
 * the Python app", which is the point: neither should ever hand the client
 * more detail than that.
 */
const UPSTREAM_UNREACHABLE_BODY = JSON.stringify({
  detail: "an unexpected error occurred",
  kind: "UpstreamUnreachable",
});

async function forwardToUpstream(input: {
  method: "GET" | "POST";
  upstreamPath: string;
  body?: BodyInit | null;
  contentType?: string;
}): Promise<Response> {
  const url = `${apiBaseUrl()}${input.upstreamPath}`;

  let upstreamResponse: Response;
  try {
    const init: RequestInit & { duplex?: "half" } = {
      method: input.method,
      headers: input.contentType ? { "content-type": input.contentType } : undefined,
      body: input.body,
    };
    if (input.body instanceof ReadableStream) {
      init.duplex = "half";
    }
    upstreamResponse = await fetch(url, init);
  } catch {
    // Deliberately no logging and no access to the caught error's own
    // message -- see the module docstring's no-leak posture.
    return new Response(UPSTREAM_UNREACHABLE_BODY, {
      status: 502,
      headers: { "content-type": "application/json" },
    });
  }

  const bodyText = await upstreamResponse.text();
  const contentType = upstreamResponse.headers.get("content-type");
  return new Response(bodyText, {
    status: upstreamResponse.status,
    headers: contentType ? { "content-type": contentType } : undefined,
  });
}

/** Dumb GET proxy: no query/body handling beyond the path itself. */
export async function proxyGet(upstreamPath: string): Promise<Response> {
  return forwardToUpstream({ method: "GET", upstreamPath });
}

/**
 * Dumb POST proxy: reads the incoming request body as raw text (never
 * parsed/re-serialized, so it reaches the upstream API byte-identical to
 * what the browser sent) and forwards it verbatim.
 */
export async function proxyJsonPost(upstreamPath: string, request: Request): Promise<Response> {
  const body = await request.text();
  return forwardToUpstream({
    method: "POST",
    upstreamPath,
    body,
    contentType: "application/json",
  });
}

/** Stream multipart bytes unchanged; never parse, text-decode, or rebuild the file. */
export async function proxyMultipartPost(
  upstreamPath: string,
  request: Request,
): Promise<Response> {
  const contentType = request.headers.get("content-type");
  if (contentType === null || !contentType.toLowerCase().startsWith("multipart/form-data;")) {
    return new Response(
      JSON.stringify({ detail: "request must be multipart/form-data", kind: "InvalidContentType" }),
      { status: 400, headers: { "content-type": "application/json" } },
    );
  }
  return forwardToUpstream({
    method: "POST",
    upstreamPath,
    body: request.body,
    contentType,
  });
}
