"""Thin FastAPI HTTP adapter over ``DisclosureApplicationService`` (T20 /
issue #28, slice 2).

    HTTP route (thin)  ->  DisclosureApplicationService  ->  existing core

Every route below does exactly this: parse/validate its request schema
(FastAPI/pydantic, via ``api.schemas``), call the application service,
map the result onto an explicit response schema, and map a known exception
onto a safe status code. Nothing else -- no treatment selection, no policy
reasoning, no summary building, no payload manipulation. See
``tests/test_api_architecture.py`` for the AST-based pin that nothing under
``application/`` or the core imports ``fastapi``/``starlette`` -- the
dependency arrow points one way only, ``api`` -> ``application`` -> core.

Two input surfaces, one application boundary:

- ``POST /disclosure/{preview,execute,compare}`` take JSON. ``file_content``
  on ``DisclosureRequestBody`` is the file's *text* content, already decoded
  client-side by the UI; it exercises the ``.txt``/``.md`` normalization path
  and cannot carry a PDF or DOCX.
- ``POST /documents/{preview,execute}`` take ``multipart/form-data`` and are
  the real structured-upload path (issue #41 gate A): the binary reaches the
  T12 ingestion boundary intact, and governance is selected by a
  server-validated preset rather than by caller-supplied policy strings.
  ``/documents/execute`` additionally requires the confirmation token its
  preview issued -- the two calls are bound to each other rather than merely
  adjacent. See their own comment block below and
  ``application/preview_confirmation.py``.

Both map onto the same ``DisclosureApplicationService`` and return the same
response schemas; they differ in how the content and the governance arrive,
and in nothing else.

Deliberate follow-ups NOT in this slice:

- API authentication/authorization and rate limiting.
- image/OCR ingestion (issue #41 defers it explicitly while PDF/DOCX work).

Request-body size is bounded by ``api/limits.RequestBodySizeLimitMiddleware``
before any route or body parser runs -- see that module for why
``application/ingestion.py``'s own ``MAX_INPUT_BYTES`` cannot cover this.

No-leak boundary (CLAUDE.md) -- three things below exist specifically for
this:

1. ``RequestValidationError`` is overridden. FastAPI/pydantic's own default
   422 body embeds each error's offending ``input`` value verbatim -- for
   this API, that input is the user's document text. The handler below
   reads only ``loc``/``type`` from each pydantic error and substitutes a
   fixed, static ``msg`` -- never pydantic's own dynamically generated
   message, so a future custom validator that happened to echo its input in
   its own message text could not leak through this path either.
2. Every 400/404 branch below returns ``str(exc)`` from an exception type
   this codebase already guarantees is safe to surface --
   ``IngestionError``, ``ContentSourceError``, ``MissingTaskError``
   (extension/kind/count only, see their own docstrings) and
   ``ExampleNotFoundError`` (names only the requested id).
3. A catch-all ``Exception`` handler returns a fixed, generic 500 body --
   never the exception's own message or a traceback. An unexpected
   exception from deep in the stack (detection, a treatment, the vault)
   could carry document content in its own ``str()``; this boundary must
   not trust that it doesn't.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from adaptive_disclosure_gateway.api import schemas
from adaptive_disclosure_gateway.api import settings as api_settings
from adaptive_disclosure_gateway.api.limits import RequestBodySizeLimitMiddleware
from adaptive_disclosure_gateway.application.contracts import (
    DisclosureApplicationRequest,
    DisclosureStrategy,
    UnsafeControlExecutionError,
)
from adaptive_disclosure_gateway.application.examples import ExampleNotFoundError
from adaptive_disclosure_gateway.application.ingestion import IngestionError
from adaptive_disclosure_gateway.application.presets import (
    DocumentAnalysisPresetError,
    list_document_presets,
)
from adaptive_disclosure_gateway.application.preview_confirmation import (
    PreviewConfirmationError,
)
from adaptive_disclosure_gateway.application.requests import ContentSourceError, MissingTaskError
from adaptive_disclosure_gateway.application.service import DisclosureApplicationService


def _build_default_service() -> DisclosureApplicationService:
    """The default demo service ``create_app()`` builds when no service is
    injected. Delegates to ``application.settings.build_default_service`` --
    the CLI adapter (``cli.py``) builds the identical default service the
    same way, so this must not become a second, independently-maintained
    copy of that construction. See ``application/settings.py``.
    """
    return api_settings.build_default_service()


def _get_service(request: Request) -> DisclosureApplicationService:
    return request.app.state.service


def _application_request_from(
    service: DisclosureApplicationService, body: schemas.DisclosureRequestBody
) -> DisclosureApplicationRequest:
    """Map one HTTP request body onto the application contract.

    Pure field mapping -- it decides nothing. Which content source is valid,
    which task/governance defaults an example contributes, and how a
    ``.txt``/``.md`` file is normalized are all decided by
    ``service.build_application_request`` in the application layer, exactly
    where they belong. Whatever that raises propagates to the registered
    exception handlers in ``create_app``.
    """
    return service.build_application_request(
        text=body.text,
        filename=body.filename,
        file_bytes=body.file_content.encode("utf-8") if body.file_content is not None else None,
        example_id=body.example_id,
        task=body.task,
        strategy=body.strategy or DisclosureStrategy.RECOMMENDED,
        governance=body.governance.to_domain() if body.governance is not None else None,
    )


def _error_response(exc: Exception, *, status_code: int) -> JSONResponse:
    body = schemas.ErrorResponse(detail=str(exc), kind=type(exc).__name__)
    return JSONResponse(status_code=status_code, content=body.model_dump())


def _document_application_request(
    service: DisclosureApplicationService,
    *,
    upload: UploadFile,
    task: str,
    document_type: str,
    analysis_mode: str | None,
    strategy: DisclosureStrategy | None,
) -> DisclosureApplicationRequest:
    """Map one multipart upload onto the application contract.

    Reads the bytes and the client-supplied filename and hands both to
    ``service.build_document_request``; decides nothing. In particular it
    does NOT forward ``upload.content_type``: the filename extension is the
    single authoritative dispatch key at the T12 boundary, and a
    client-declared MIME type must not be able to select a parser (see
    ``service.build_document_request``'s docstring).

    The bytes are read into memory and never written to disk -- the upload
    is ephemeral by default (issue #28/#41), and the only bound on how much
    can arrive here is ``RequestBodySizeLimitMiddleware``, which has already
    run by this point.
    """
    return service.build_document_request(
        filename=upload.filename or "",
        file_bytes=upload.file.read(),
        task=task,
        document_type=document_type,
        analysis_mode=analysis_mode,
        strategy=strategy or DisclosureStrategy.RECOMMENDED,
    )


def create_app(
    service: DisclosureApplicationService | None = None,
    *,
    allowed_origins: Sequence[str] = (),
    max_upload_bytes: int | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    ``service`` is injectable so tests never depend on environment/config --
    they always pass their own ``DisclosureApplicationService`` wired to a
    real core with a fixture provider. When ``None``, a default demo service
    is built from ``api/settings.py``'s environment-driven configuration.

    ``allowed_origins`` configures CORS. An explicit, non-empty value always
    wins. Otherwise: for an injected ``service`` (the test path), CORS stays
    empty -- tests must not depend on the deployment environment either. For
    the default demo service (``service=None``), it falls back to
    ``ADG_ALLOWED_ORIGINS`` (empty by default). Never defaults to ``"*"`` --
    issue #28 requires this be deployment-configurable for T25/#42.
    """
    app = FastAPI(title="Adaptive Disclosure Gateway API")
    app.state.service = service if service is not None else _build_default_service()

    resolved_origins = tuple(allowed_origins)
    if not resolved_origins and service is None:
        resolved_origins = api_settings.allowed_origins()

    resolved_max_upload_bytes = max_upload_bytes
    if resolved_max_upload_bytes is None:
        resolved_max_upload_bytes = (
            api_settings.max_upload_bytes()
            if service is None
            else api_settings.DEFAULT_MAX_UPLOAD_BYTES
        )

    # Added BEFORE the CORS middleware on purpose. Starlette applies the
    # most recently added middleware outermost, so this ordering puts CORS
    # outside the size limit -- which means the 413 a browser gets still
    # carries the CORS headers it needs to read the status at all. The size
    # limit still runs before the router and therefore before any body is
    # parsed.
    app.add_middleware(RequestBodySizeLimitMiddleware, max_bytes=resolved_max_upload_bytes)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved_origins),
        allow_credentials=bool(resolved_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        items = [
            schemas.ValidationErrorItem(
                loc=[str(part) for part in error["loc"]],
                type=error["type"],
                # A fixed, static message -- deliberately never error["msg"]
                # or error["input"]. See the module docstring's no-leak
                # section, point 1.
                msg="request body failed validation",
            )
            for error in exc.errors()
        ]
        body = schemas.ValidationErrorResponse(detail=items)
        return JSONResponse(status_code=422, content=body.model_dump())

    @app.exception_handler(IngestionError)
    @app.exception_handler(ContentSourceError)
    @app.exception_handler(MissingTaskError)
    @app.exception_handler(DocumentAnalysisPresetError)
    @app.exception_handler(PreviewConfirmationError)
    @app.exception_handler(UnsafeControlExecutionError)
    async def _handle_bad_request(_request: Request, exc: Exception) -> JSONResponse:
        # Registered once, for every route, rather than repeated as a
        # per-route try/except: this is the single place a caller-input
        # error becomes an HTTP body, so the no-leak guarantee about which
        # exception messages may be surfaced (module docstring, point 2)
        # is enforced in exactly one place instead of once per endpoint.
        # ``DocumentAnalysisPresetError`` joins this set for the same
        # reason: its message names only the server's own supported document
        # types/analysis modes, never the token the caller sent.
        # ``PreviewConfirmationError`` carries one fixed constant message
        # for every failure mode -- never the confirmation token, the
        # recomputed state, the document, the task or the payload -- and
        # ``UnsafeControlExecutionError`` names only the treatment class and
        # the surface. Both are 400 rather than 200-with-an-outcome because
        # nothing was executed at all: unlike a blocked disclosure or a
        # failed provider call, these are refusals to run the request, not
        # results of running it.
        return _error_response(exc, status_code=400)

    @app.exception_handler(ExampleNotFoundError)
    async def _handle_example_not_found(_request: Request, exc: Exception) -> JSONResponse:
        return _error_response(exc, status_code=404)

    @app.exception_handler(Exception)
    async def _handle_unexpected_exception(_request: Request, _exc: Exception) -> JSONResponse:
        # Deliberately never _exc's own message or traceback -- see the
        # module docstring's no-leak section, point 3.
        return JSONResponse(
            status_code=500,
            content=schemas.ErrorResponse(
                detail="an unexpected error occurred", kind="InternalServerError"
            ).model_dump(),
        )

    @app.get("/health", response_model=None)
    def health(request: Request) -> dict[str, object]:
        service = _get_service(request)
        return schemas.HealthResponse.from_domain(service.describe_health()).model_dump()

    @app.get("/examples", response_model=None)
    def list_examples(request: Request) -> dict[str, object]:
        service = _get_service(request)
        return schemas.ExamplesResponse.from_domain(service.list_examples()).model_dump()

    @app.get("/strategies", response_model=None)
    def list_strategies(request: Request) -> dict[str, object]:
        service = _get_service(request)
        return schemas.StrategiesResponse.from_domain(service.list_strategies()).model_dump()

    @app.post("/disclosure/preview", response_model=None)
    def preview_disclosure(body: schemas.DisclosureRequestBody, request: Request) -> JSONResponse:
        service = _get_service(request)
        application_request = _application_request_from(service, body)

        preview = service.preview(application_request)
        content = schemas.PreviewResponse.from_domain(preview).model_dump()
        return JSONResponse(status_code=200, content=content)

    @app.post("/disclosure/compare", response_model=None)
    def compare_disclosure(body: schemas.DisclosureRequestBody, request: Request) -> JSONResponse:
        """Run the SAME content through every B0-B4 strategy
        (``service.compare_strategies``) and return all five previews side
        by side -- never a provider call, for any of them.

        ``body.strategy`` is deliberately ignored here: unlike
        ``/disclosure/preview``/``/disclosure/execute``, where it selects
        which single strategy to run, a comparison always covers all five
        regardless of what a caller supplied for it. This route still
        accepts the same shared ``DisclosureRequestBody`` (rather than a
        second, near-identical schema) so a client can point one existing
        request payload at either endpoint.
        """
        service = _get_service(request)
        application_request = _application_request_from(service, body)

        comparison = service.compare_strategies(application_request)
        content = schemas.CompareResponse.from_domain(comparison).model_dump()
        return JSONResponse(status_code=200, content=content)

    @app.post("/disclosure/execute", response_model=None)
    def execute_disclosure(body: schemas.DisclosureRequestBody, request: Request) -> JSONResponse:
        service = _get_service(request)
        application_request = _application_request_from(service, body)

        # A blocked request, or a failed provider call, is NOT an HTTP
        # error -- both are legitimate outcomes of a real disclosure
        # decision, already recorded as metadata on the result itself
        # (summary.status / provider.failed+failure_kind). This route
        # returns 200 either way.
        execution = service.execute(application_request)
        content = schemas.ExecuteResponse.from_domain(execution).model_dump()
        return JSONResponse(status_code=200, content=content)

    # --- structured document upload ------------------------------------------
    #
    # The binary entry point for the advisor contract demo (issue #41 gate
    # A). Three routes, matching the existing /disclosure ones exactly in
    # shape and response schema:
    #
    #   multipart HTTP -> service.build_document_request -> T12 ingestion
    #     -> NormalizedContent -> the same preview/execute the JSON routes use
    #
    # Nothing about preview/execute/comparison/governance is reimplemented
    # here; these routes differ from /disclosure/* in their *input* only.
    # ``document_type`` is a required form field, so an uploaded contract can
    # never fall through to the deployer's default (HR) governance.
    #
    # There is deliberately no single "upload and answer" route. Upload +
    # preview is one request, the confirmed execute is another, and the
    # reviewer's confirmation happens between them -- that separation is the
    # product, not an implementation detail. The cost is that the file is
    # uploaded twice for a confirmed run; the alternative is server-side
    # retention of the uploaded document between the two calls, which is
    # exactly what "no persistent storage of uploaded source documents by
    # default" forbids.
    #
    # Two separate requests are not by themselves a review step, though.
    # Until the preview confirmation existed, a client could preview under
    # `recommended`/B4 and execute the same upload under `strategy=b0`: the
    # separation was there and the guarantee was not. `/documents/preview`
    # therefore issues a server-signed token over what it showed, and
    # `/documents/execute` requires it and re-computes that state from its
    # own request before the provider is reachable. The binding lives in the
    # application layer (`application/preview_confirmation.py` and
    # `DisclosureApplicationService.{preview,execute}_document`); these
    # routes only carry the token, exactly as this adapter carries
    # everything else.

    @app.get("/documents/types", response_model=None)
    def list_document_types(_request: Request) -> dict[str, object]:
        """The caller-facing upload vocabulary, so a UI never hardcodes it.

        Pure data from ``application/presets.py``; exposes no policy
        version, domain or role -- see ``schemas.DocumentTypeModel``.
        """
        return schemas.DocumentTypesResponse.from_domain(list_document_presets()).model_dump()

    @app.post("/documents/preview", response_model=None)
    def preview_document(
        request: Request,
        file: Annotated[UploadFile, File()],
        task: Annotated[str, Form()],
        document_type: Annotated[str, Form()],
        analysis_mode: Annotated[str | None, Form()] = None,
        strategy: Annotated[DisclosureStrategy | None, Form()] = None,
    ) -> JSONResponse:
        """The review half of preview -> confirm -> execute.

        Returns the same review the JSON routes return, plus the
        ``confirmation_token`` the matching ``/documents/execute`` requires.
        The token is what makes the two stateless calls one flow -- see
        ``application/preview_confirmation.py``.
        """
        service = _get_service(request)
        application_request = _document_application_request(
            service,
            upload=file,
            task=task,
            document_type=document_type,
            analysis_mode=analysis_mode,
            strategy=strategy,
        )

        document_preview = service.preview_document(application_request)
        content = schemas.DocumentPreviewResponse.from_document_preview(
            document_preview
        ).model_dump()
        return JSONResponse(status_code=200, content=content)

    @app.post("/documents/execute", response_model=None)
    def execute_document(
        request: Request,
        file: Annotated[UploadFile, File()],
        task: Annotated[str, Form()],
        document_type: Annotated[str, Form()],
        confirmation_token: Annotated[str, Form()],
        analysis_mode: Annotated[str | None, Form()] = None,
        strategy: Annotated[DisclosureStrategy | None, Form()] = None,
    ) -> JSONResponse:
        """The confirmed half of preview -> confirm -> execute.

        ``confirmation_token`` is REQUIRED, and is the whole reason this
        route is not simply "preview, but also call the provider". The
        service re-normalizes the re-uploaded file, re-resolves the
        governance and the treatment, recomputes the state that would be
        disclosed, and only then checks the token against it. Any divergence
        from the approved review -- a different document, task, analysis
        mode, strategy, resolved policy or provider class -- is refused
        before the provider is contacted.

        Like ``POST /disclosure/execute``, a blocked request or a failed
        provider call is a legitimate outcome recorded on the result, not an
        HTTP error: this returns 200 in those cases. A failed confirmation
        is different in kind -- nothing was executed at all -- and is a 400
        through ``PreviewConfirmationError``.
        """
        service = _get_service(request)
        application_request = _document_application_request(
            service,
            upload=file,
            task=task,
            document_type=document_type,
            analysis_mode=analysis_mode,
            strategy=strategy,
        )

        execution = service.execute_document(
            application_request, confirmation_token=confirmation_token
        )
        content = schemas.ExecuteResponse.from_domain(execution).model_dump()
        return JSONResponse(status_code=200, content=content)

    return app
