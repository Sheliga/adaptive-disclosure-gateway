"""Server-side governance presets for the advisor contract demo (T20 /
issue #28, demo-integration slice; issue #41 gate A).

What these tests exist to catch -- each is a real defect the preset
mechanism could plausibly have:

- a contract uploaded by the UI being silently analysed under the server's
  HR defaults (``domain=hr`` / ``hr-v1``), which is issue #41's blocker 4;
- the frontend being able to invent policy semantics: an arbitrary
  ``domain``/``policy_version``/``purpose`` string travelling from the
  browser straight onto a ``GovernanceContext``;
- an unknown document type or analysis mode *defaulting* to something
  instead of failing closed;
- a preset claiming a ``provider_class``, which is a deployment fact and
  not a scenario fact (the same reasoning
  ``application/requests.py::_EXAMPLE_OVERRIDE_FIELDS`` already records for
  prepared examples);
- the preset being decorative -- resolving the right strings while the
  disclosure decision is unchanged.
"""

from __future__ import annotations

import traceback

import pytest

from adaptive_disclosure_gateway.application.contracts import DisclosureStrategy
from adaptive_disclosure_gateway.application.ingestion import IngestionError, ParsedDocument
from adaptive_disclosure_gateway.application.presets import (
    CONTRACT_DOCUMENT_TYPE,
    DocumentAnalysisPresetError,
    list_document_presets,
    resolve_governance_preset,
)
from adaptive_disclosure_gateway.application.service import DisclosureApplicationService
from adaptive_disclosure_gateway.domain import Treatment
from adaptive_disclosure_gateway.policies import PolicyRepository
from adaptive_disclosure_gateway.providers import FakeProvider
from tests.api_support import POLICY_DIR, default_context
from tests.contracts_fixture import (
    CONTRACTING_PARTY,
    CONTRACTS_FIXTURE,
)

CONTRACT_TASK = "Summarize the obligations of each party and the deadlines."


class StubContractParser:
    """A ``DocumentParser`` double standing in for Docling.

    Deterministic and offline: the real Docling conversion can require
    cached model artifacts (see ``tests/test_application_ingestion_docling.py``),
    so the always-on tests inject this and the opt-in integration tests
    exercise the real parser. It returns the project-owned ``ParsedDocument``
    the T12 boundary contracts for -- never a parser-native object.
    """

    parser_name = "stub_document_parser"
    parser_version = "test"

    def __init__(self, text: str = CONTRACTS_FIXTURE) -> None:
        self._text = text
        self.calls: list[str] = []

    def parse(self, *, safe_name: str, data: bytes) -> ParsedDocument:
        self.calls.append(safe_name)
        return ParsedDocument(text=self._text)


def build_service(
    provider=None, *, document_parser=None, **context_overrides
) -> DisclosureApplicationService:
    return DisclosureApplicationService(
        policy_repository=PolicyRepository.from_directory(POLICY_DIR),
        provider=provider if provider is not None else FakeProvider(),
        default_context=default_context(**context_overrides),
        document_parser=document_parser,
    )


# --- the preset itself -------------------------------------------------------


def test_the_contract_preset_resolves_to_the_contracts_domain_and_contracts_v1_policy():
    overrides = resolve_governance_preset(CONTRACT_DOCUMENT_TYPE, analysis_mode=None)

    assert overrides.domain == "contracts"
    assert overrides.policy_version == "contracts-v1"


def test_an_unknown_document_type_fails_closed_instead_of_defaulting_to_hr():
    with pytest.raises(DocumentAnalysisPresetError):
        resolve_governance_preset("some_unregistered_type", analysis_mode=None)


def test_an_arbitrary_analysis_mode_cannot_become_a_governance_purpose():
    # The frontend must not be able to invent policy semantics: `purpose` is
    # read by contracts-v1's purpose_actions, so a free-form purpose string
    # would be a client-controlled governance decision.
    with pytest.raises(DocumentAnalysisPresetError):
        resolve_governance_preset(CONTRACT_DOCUMENT_TYPE, analysis_mode="financial_audit ")


def test_the_preset_error_names_the_supported_options_and_echoes_no_caller_string():
    marker = "Aurora-Servicos-Digitais-MARKER"
    with pytest.raises(DocumentAnalysisPresetError) as excinfo:
        resolve_governance_preset(marker, analysis_mode=None)

    message = str(excinfo.value)
    assert marker not in message
    assert CONTRACT_DOCUMENT_TYPE in message


@pytest.mark.parametrize("analysis_mode", ["financial_audit", "compliance_review"])
def test_each_allowlisted_analysis_mode_becomes_exactly_that_purpose(analysis_mode: str):
    overrides = resolve_governance_preset(CONTRACT_DOCUMENT_TYPE, analysis_mode=analysis_mode)

    assert overrides.purpose == analysis_mode


def test_a_preset_never_declares_a_provider_class():
    # provider_class is a deployment fact owned by whoever configured the
    # service's Provider -- never by a document-type preset. Letting a
    # preset name one would re-create exactly the failure
    # application/requests.py records for prepared examples.
    for preset in list_document_presets():
        overrides = resolve_governance_preset(
            preset.document_type, analysis_mode=preset.default_analysis_mode
        )
        assert overrides.provider_class is None


def test_a_preset_never_declares_a_lifecycle_identifier():
    for preset in list_document_presets():
        overrides = resolve_governance_preset(
            preset.document_type, analysis_mode=preset.default_analysis_mode
        )
        assert overrides.session_id is None
        assert overrides.document_id is None
        assert overrides.request_id is None
        assert overrides.requester_id is None


# --- the preset reaching the disclosure decision -----------------------------


def test_a_contract_upload_is_normalized_through_the_t12_boundary():
    parser = StubContractParser()
    service = build_service(document_parser=parser)

    request = service.build_document_request(
        filename="contract.pdf",
        file_bytes=b"%PDF-1.4 synthetic",
        task=CONTRACT_TASK,
        document_type=CONTRACT_DOCUMENT_TYPE,
    )

    assert parser.calls == ["uploaded.pdf"], "the parser must receive a generated safe name only"
    assert request.content.source_kind == "document_file"
    assert request.content.media_type == "application/pdf"
    assert request.content.parser_name == "stub_document_parser"
    assert request.content.text == CONTRACTS_FIXTURE


def test_a_contract_upload_previews_under_contracts_v1_even_though_the_server_default_is_hr():
    service = build_service(document_parser=StubContractParser())

    request = service.build_document_request(
        filename="contract.pdf",
        file_bytes=b"%PDF-1.4 synthetic",
        task=CONTRACT_TASK,
        document_type=CONTRACT_DOCUMENT_TYPE,
    )
    preview = service.preview(request)

    assert preview.governance.domain == "contracts"
    assert preview.governance.policy_version == "contracts-v1"
    assert preview.treatment is Treatment.POLICY_GOVERNED


def test_the_contracts_preset_is_load_bearing_not_decorative():
    """The same synthetic contract, same task, same service -- only the
    governance preset differs.

    Under the server's HR defaults, contracts-v1's categories have no rule
    in ``hr-v1``, so every one of them fails closed to BLOCK_REQUEST and the
    request is blocked. Under the Contracts preset the request is allowed
    and the contracting party's identity does not reach the payload. If the
    preset were ever reduced to a label that did not actually reach
    ``GovernanceContext``, this test fails.
    """
    service = build_service(document_parser=StubContractParser())

    contracts_preview = service.preview(
        service.build_document_request(
            filename="contract.pdf",
            file_bytes=b"%PDF-1.4 synthetic",
            task=CONTRACT_TASK,
            document_type=CONTRACT_DOCUMENT_TYPE,
        )
    )
    hr_preview = service.preview(
        service.build_application_request(
            filename="contract.pdf",
            file_bytes=b"%PDF-1.4 synthetic",
            task=CONTRACT_TASK,
            strategy=DisclosureStrategy.RECOMMENDED,
        )
    )

    # DisclosureSummary.status is a plain Literal["allowed", "blocked"]
    # string, never the DisclosureOutcome enum -- an `is` comparison against
    # the enum member would pass vacuously for BOTH previews and pin nothing.
    assert contracts_preview.summary.status == "allowed"
    assert CONTRACTING_PARTY not in contracts_preview.external_payload
    assert hr_preview.summary.status == "blocked"


def test_an_unsupported_upload_extension_fails_closed_before_any_parser_runs():
    parser = StubContractParser()
    service = build_service(document_parser=parser)

    with pytest.raises(IngestionError):
        service.build_document_request(
            filename="contract.exe",
            file_bytes=b"MZ synthetic",
            task=CONTRACT_TASK,
            document_type=CONTRACT_DOCUMENT_TYPE,
        )

    assert parser.calls == []


def test_a_parser_failure_never_echoes_the_document_text_or_bytes():
    marker = "Aurora Servicos Digitais Ltda"

    class EchoingParser:
        parser_name = "echoing"
        parser_version = "test"

        def parse(self, *, safe_name: str, data: bytes) -> ParsedDocument:
            raise RuntimeError(f"parser blew up on {marker}: {data!r}")

    service = build_service(document_parser=EchoingParser())

    with pytest.raises(IngestionError) as excinfo:
        service.build_document_request(
            filename="contract.pdf",
            file_bytes=marker.encode("utf-8"),
            task=CONTRACT_TASK,
            document_type=CONTRACT_DOCUMENT_TYPE,
        )

    assert marker not in str(excinfo.value)
    # The chain is broken at the raise site (`raise ... from None`), so the
    # parser's own message -- which here echoes both the document text and
    # its raw bytes -- cannot resurface through a full traceback dump
    # either. This is the assertion that matters: `__context__` is still
    # set by the interpreter, but `__suppress_context__` is what every
    # traceback formatter, logger and error reporter honours.
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__suppress_context__ is True
    rendered = "".join(
        traceback.format_exception(type(excinfo.value), excinfo.value, excinfo.value.__traceback__)
    )
    assert marker not in rendered
