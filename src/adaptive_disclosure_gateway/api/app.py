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

Deliberate follow-ups NOT in this slice:

- multipart/binary file upload. ``file_content`` on
  ``DisclosureRequestBody`` is the file's *text* content, already decoded
  client-side by the UI -- this route encodes it back to UTF-8 bytes and
  hands it to ``build_application_request`` purely so the real
  ``.txt``/``.md`` normalization/validation path in ``application/ingestion.py``
  is genuinely exercised, not to support a general file-upload contract.
  A real multipart endpoint is future work, most naturally once T12/Docling
  (issue #9) adds non-text formats.
- API authentication/authorization and rate limiting.

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

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from adaptive_disclosure_gateway.api import schemas
from adaptive_disclosure_gateway.api import settings as api_settings
from adaptive_disclosure_gateway.application.contracts import (
    DisclosureApplicationRequest,
    DisclosureStrategy,
)
from adaptive_disclosure_gateway.application.examples import ExampleNotFoundError
from adaptive_disclosure_gateway.application.ingestion import IngestionError
from adaptive_disclosure_gateway.application.requests import ContentSourceError, MissingTaskError
from adaptive_disclosure_gateway.application.service import DisclosureApplicationService
from adaptive_disclosure_gateway.policies import PolicyRepository
from adaptive_disclosure_gateway.providers import FakeProvider


def _build_default_service() -> DisclosureApplicationService:
    """The default demo service ``create_app()`` builds when no service is
    injected: the real policy repository and HR pilot examples from this
    checkout, a deterministic ``FakeProvider`` (issue #29 requires this be
    clearly labeled -- see ``GET /health``'s ``deterministic_demo_mode``),
    and a documented default ``GovernanceContext``. See ``api/settings.py``.
    """
    return DisclosureApplicationService(
        policy_repository=PolicyRepository.from_directory(api_settings.policy_directory()),
        provider=FakeProvider(),
        default_context=api_settings.default_governance_context(),
        examples_directory=api_settings.examples_directory(),
    )


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


def create_app(
    service: DisclosureApplicationService | None = None,
    *,
    allowed_origins: Sequence[str] = (),
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
    async def _handle_bad_request(_request: Request, exc: Exception) -> JSONResponse:
        # Registered once, for every route, rather than repeated as a
        # per-route try/except: this is the single place a caller-input
        # error becomes an HTTP body, so the no-leak guarantee about which
        # exception messages may be surfaced (module docstring, point 2)
        # is enforced in exactly one place instead of once per endpoint.
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

    return app
