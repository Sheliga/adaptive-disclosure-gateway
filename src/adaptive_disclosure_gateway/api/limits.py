"""Request-body size enforcement at the HTTP accepting boundary (T20 /
issue #28's demo-integration slice; issue #41 gate A).

Why this exists even though ingestion already has a limit
---------------------------------------------------------

``application/ingestion.py`` already enforces ``MAX_INPUT_BYTES`` (10 MiB)
and rejects early. That limit is real, but it can only act on bytes that
have already been received and assembled: by the time
``normalize_text_file`` is called, the whole body is in memory. The gap this
module closes is upstream of that -- an unauthenticated caller posting a
multi-gigabyte body would have it buffered by the ASGI server and the
framework's multipart parser before any application code ran.

So this is a pure ASGI middleware, not a FastAPI dependency: it must run
*before* the request body is read, and a dependency cannot.

Two enforcement paths, and both are required
--------------------------------------------

1. **Declared length.** If ``Content-Length`` exceeds the limit, the request
   is refused immediately -- ``receive`` is never called, so not one byte of
   the body is pulled off the socket by this application.
2. **Streamed length.** A client may omit ``Content-Length`` entirely
   (``Transfer-Encoding: chunked``), or declare one and send more. Every
   body chunk is therefore also counted as it arrives, and the request is
   aborted the moment the running total passes the limit. Without this the
   browser (or a well-behaved client's own header) would be the only
   protection, which is no protection at all.

No-leak invariant (CLAUDE.md): the 413 body names the configured limit in
bytes and nothing else -- never the received byte count of the offending
body beyond the limit itself, never a filename, and never any part of the
content. It is a fixed-shape ``ErrorResponse``, identical to every other
error this API emits.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

DEFAULT_MAX_UPLOAD_BYTES = 8 * 1024 * 1024
"""The demo's conservative HTTP request-body ceiling, 8 MiB.

Deliberately *below* ``application/ingestion.MAX_INPUT_BYTES`` (10 MiB) so
that for an upload the HTTP boundary is always the binding limit and an
oversized body is refused before any normalization or parser work begins --
pinned by ``tests/test_api_documents_upload.py``. It is an engineering
safety limit for a small controlled research demo, not a scientific
parameter; ``ADG_MAX_UPLOAD_BYTES`` overrides it for a deployment that needs
a different one.
"""

TOO_LARGE_STATUS_CODE = 413

Scope = dict[str, Any]
Message = dict[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


class _RequestBodyTooLarge(Exception):
    """Internal signal raised from the counting ``receive`` wrapper.

    Never surfaced to a caller and never carries a byte count of the body --
    the response body is built from the configured limit alone.
    """


def _declared_content_length(scope: Scope) -> int | None:
    for name, value in scope.get("headers", ()):
        if name.lower() != b"content-length":
            continue
        try:
            return int(value)
        except ValueError:
            # A malformed Content-Length is not this middleware's problem to
            # diagnose; the server/framework rejects it on its own. Falling
            # through to the streaming counter keeps the limit enforced
            # either way.
            return None
    return None


def _too_large_body(max_bytes: int) -> bytes:
    return json.dumps(
        {
            "detail": (f"request body exceeds the configured limit of {max_bytes} bytes"),
            "kind": "RequestBodyTooLarge",
        }
    ).encode("utf-8")


class RequestBodySizeLimitMiddleware:
    """Refuse any HTTP request whose body exceeds ``max_bytes``.

    Applies to every route, not just the upload ones: a JSON body on
    ``/disclosure/preview`` can be just as large as a multipart one, and a
    limit that has to be remembered per route is a limit that will be
    forgotten on the next route.
    """

    def __init__(self, app: ASGIApp, *, max_bytes: int = DEFAULT_MAX_UPLOAD_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        declared = _declared_content_length(scope)
        if declared is not None and declared > self.max_bytes:
            await self._send_too_large(send)
            return

        received = 0
        exceeded = False
        forwarded_start = False
        answered = False

        async def counting_receive() -> Message:
            nonlocal received, exceeded
            message = await receive()
            if message.get("type") == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    exceeded = True
                    raise _RequestBodyTooLarge
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal forwarded_start, answered
            if exceeded and not forwarded_start:
                # The application is about to answer a request whose body
                # this middleware cut off mid-stream. Its answer describes
                # the truncation, not the cause -- FastAPI's multipart
                # handling, for instance, catches every exception raised by
                # the body stream and reports a generic 400. Replace it with
                # the 413 that actually describes what happened, and drop
                # the rest of that response.
                if not answered:
                    answered = True
                    await self._send_too_large(send)
                return
            if message.get("type") == "http.response.start":
                forwarded_start = True
            await send(message)

        try:
            await self.app(scope, counting_receive, guarded_send)
        except _RequestBodyTooLarge:
            if forwarded_start:
                # A status line is already committed on the wire; there is
                # nothing safe left to send, so let the server tear the
                # connection down.
                raise
            if not answered:
                answered = True
                await self._send_too_large(send)

    async def _send_too_large(self, send: Send) -> None:
        body = _too_large_body(self.max_bytes)
        await send(
            {
                "type": "http.response.start",
                "status": TOO_LARGE_STATUS_CODE,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
