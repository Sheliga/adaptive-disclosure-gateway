"""Opt-in end-to-end smoke test for the deployed advisor demo stack (T25 /
issue #42).

Skipped unless ``ADG_DEMO_SMOKE_BASE_URL`` names a running **web** origin
(e.g. ``http://localhost:3000``) -- the same opt-in pattern
``ADG_RUN_DOCLING_INTEGRATION``/``ADG_RUN_ANTHROPIC_INTEGRATION`` already
use for artifacts this repository's baseline test run must not require.
Every request below targets the web origin's own ``/api/**`` routes, never
the Python API directly: that is the real topology an advisor's browser
uses (``docs/advisor-demo.md``'s architectural boundary, and
``web/lib/proxy.ts``'s module docstring), and a test that reached the API
container directly would not actually exercise the web container, its
healthcheck, or the runtime-configured ``ADG_API_BASE_URL`` at all.

Content is entirely synthetic -- invented parties, tax ids and amounts, in
the same spirit as ``tests/contracts_fixture.py`` -- and is generated at
test time, never a checked-in binary. PDF/DOCX bytes are built with
``tests/document_fixtures.py``'s ``minimal_pdf_bytes``/``minimal_docx_bytes``
(the same builders ``tests/test_application_ingestion_docling.py`` and
``tests/test_api_documents_upload.py`` already rely on), so both formats go
through the same real Docling code path any advisor's upload would.
"""

from __future__ import annotations

import os
from collections.abc import Iterable

import pytest

httpx = pytest.importorskip("httpx")

from tests.document_fixtures import minimal_docx_bytes, minimal_pdf_bytes

_BASE_URL_ENV_VAR = "ADG_DEMO_SMOKE_BASE_URL"

pytestmark = pytest.mark.skipif(
    not os.environ.get(_BASE_URL_ENV_VAR, "").strip(),
    reason=(
        f"opt-in E2E smoke test: set {_BASE_URL_ENV_VAR} to a running demo web origin "
        "(e.g. http://localhost:3000) to run it"
    ),
)

_REQUEST_TIMEOUT_SECONDS = 60.0
_EXECUTE_TIMEOUT_SECONDS = 120.0

# --- synthetic contract content ---------------------------------------------
#
# Every party, representative, tax id, amount and date below is invented for
# this test. No employer, client or counterparty document contributed a
# single value -- see tests/contracts_fixture.py for the sibling fixture
# this one deliberately does not reuse verbatim (independent values, so a
# regression in one is not masked by a coincidence in the other).

PARTY_A = "Solstice Harbor Consultoria Ltda"
PARTY_B = "Meridian Vale Engenharia SA"
REPRESENTATIVE = "Helena Duarte Nascimento"
CNPJ_A = "11.222.333/0001-44"
CNPJ_B = "55.666.777/0001-88"
REPRESENTATIVE_CPF = "987.654.321-00"
CONTRACT_VALUE = "R$ 3750000.00"
PENALTY_AMOUNT = "R$ 45000.00"
DEADLINE = "2027-01-15"

_CONTRACT_LINES = (
    "CONTRACT",
    f"Contracting party: {PARTY_A}",
    f"CNPJ: {CNPJ_A}",
    f"Contracted party: {PARTY_B}",
    f"CNPJ: {CNPJ_B}",
    f"Representative: {REPRESENTATIVE}",
    f"CPF: {REPRESENTATIVE_CPF}",
    f"Contract value: {CONTRACT_VALUE}",
    f"Penalty: {PENALTY_AMOUNT}",
    f"Deadline: {DEADLINE}",
)

#: Every sensitive original value contracts-v1 governs, for the no-leak scan.
SENSITIVE_VALUES: tuple[str, ...] = (
    PARTY_A,
    PARTY_B,
    REPRESENTATIVE,
    CNPJ_A,
    CNPJ_B,
    REPRESENTATIVE_CPF,
    CONTRACT_VALUE,
    PENALTY_AMOUNT,
)

TASK = "Summarize the obligations and financial terms of this contract."
DOCUMENT_TYPE = "contract"
ANALYSIS_MODE = "contract_summary"


def _base_url() -> str:
    return os.environ[_BASE_URL_ENV_VAR].rstrip("/")


def _get(path: str) -> httpx.Response:
    return httpx.get(f"{_base_url()}{path}", timeout=_REQUEST_TIMEOUT_SECONDS)


def _preview(
    file_bytes: bytes,
    filename: str,
    *,
    strategy: str | None = None,
    timeout: float = _REQUEST_TIMEOUT_SECONDS,
) -> httpx.Response:
    data = {"task": TASK, "document_type": DOCUMENT_TYPE, "analysis_mode": ANALYSIS_MODE}
    if strategy is not None:
        data["strategy"] = strategy
    files = {"file": (filename, file_bytes, "application/octet-stream")}
    return httpx.post(
        f"{_base_url()}/api/documents/preview", data=data, files=files, timeout=timeout
    )


def _execute(
    file_bytes: bytes,
    filename: str,
    *,
    confirmation_token: str,
    strategy: str | None = None,
    timeout: float = _EXECUTE_TIMEOUT_SECONDS,
) -> httpx.Response:
    data = {
        "task": TASK,
        "document_type": DOCUMENT_TYPE,
        "analysis_mode": ANALYSIS_MODE,
        "confirmation_token": confirmation_token,
    }
    if strategy is not None:
        data["strategy"] = strategy
    files = {"file": (filename, file_bytes, "application/octet-stream")}
    return httpx.post(
        f"{_base_url()}/api/documents/execute", data=data, files=files, timeout=timeout
    )


def _assert_no_sensitive_value(haystack: str, values: Iterable[str]) -> None:
    for value in values:
        assert value not in haystack, "a synthetic sensitive value leaked into the payload"


class TestHealthAndVocabulary:
    def test_health_reports_ok(self) -> None:
        body = _get("/api/health").raise_for_status().json()
        assert body["status"] == "ok"
        assert "provider" in body

    def test_documents_types_includes_contract(self) -> None:
        body = _get("/api/documents/types").raise_for_status().json()
        document_types = {entry["document_type"] for entry in body["document_types"]}
        assert DOCUMENT_TYPE in document_types


@pytest.mark.parametrize(
    ("filename", "build_bytes"),
    [
        ("synthetic-contract.pdf", lambda: minimal_pdf_bytes(_CONTRACT_LINES)),
        ("synthetic-contract.docx", lambda: minimal_docx_bytes(_CONTRACT_LINES)),
    ],
)
class TestPreviewConfirmExecute:
    """The full preview -> confirm -> execute path through the web origin,
    for both Docling-backed formats the demo accepts.
    """

    def test_preview_confirm_execute_round_trip(self, filename: str, build_bytes) -> None:
        file_bytes = build_bytes()

        preview_response = _preview(file_bytes, filename)
        assert preview_response.status_code == 200, preview_response.text
        preview_body = preview_response.json()

        # The whole point of preview -> confirm -> execute: contracts-v1
        # must not let the synthetic party names/tax ids/amounts reach what
        # would leave the trust boundary.
        _assert_no_sensitive_value(preview_body["external_payload"], SENSITIVE_VALUES)

        confirmation_token = preview_body["confirmation_token"]
        assert confirmation_token

        execute_response = _execute(file_bytes, filename, confirmation_token=confirmation_token)
        assert execute_response.status_code == 200, execute_response.text
        execute_body = execute_response.json()

        assert execute_body["status"] in {"allowed", "blocked"}
        # A provider failure is a legitimate recorded outcome, never an HTTP
        # error (see docs/provider-configuration.md's "Behaviour with no
        # credential": a misconfigured real provider fails closed here
        # rather than falling back to FakeProvider) -- this test deliberately
        # does not assume the target deployment has a WORKING real provider
        # configured. What it can assert unconditionally: an allowed
        # disclosure whose provider call actually succeeded must produce a
        # real, non-empty reconstructed answer.
        if execute_body["status"] == "allowed" and not execute_body["provider"]["failed"]:
            assert execute_body["final_answer"], execute_body


class TestB0DirectSurfaceRule:
    """B0 -- Direct stays visible in preview/comparison but must never
    execute against a provider outside the trust boundary
    (docs/advisor-demo.md's "B0 -- Direct on the document surface"). Against
    the deterministic FakeProvider it is allowed to run, because nothing
    leaves the process.
    """

    def test_b0_execute_refused_only_when_provider_is_external(self) -> None:
        health = _get("/api/health").raise_for_status().json()
        is_external = not health["provider"]["deterministic_demo_mode"]

        file_bytes = minimal_pdf_bytes(_CONTRACT_LINES)
        preview_response = _preview(file_bytes, "synthetic-contract-b0.pdf", strategy="b0")
        assert preview_response.status_code == 200, preview_response.text
        confirmation_token = preview_response.json()["confirmation_token"]

        execute_response = _execute(
            file_bytes,
            "synthetic-contract-b0.pdf",
            confirmation_token=confirmation_token,
            strategy="b0",
        )

        if is_external:
            assert execute_response.status_code == 400, execute_response.text
            assert execute_response.json()["kind"] == "UnsafeControlExecutionError"
        else:
            assert execute_response.status_code == 200, execute_response.text


class TestRequestSizeLimit:
    def test_oversized_body_gets_413_through_web_origin(self) -> None:
        # Comfortably above the demo's default 8 MiB ceiling
        # (ADG_MAX_UPLOAD_BYTES) without depending on the deployment's exact
        # configured value.
        oversized = b"0" * (16 * 1024 * 1024)
        response = _preview(oversized, "oversized.pdf", timeout=_EXECUTE_TIMEOUT_SECONDS)
        assert response.status_code == 413, response.text
