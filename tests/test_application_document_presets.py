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
  disclosure decision is unchanged;
- an uploaded document being executable through a path that checks no
  preview confirmation, so what reaches the provider need not be what a
  reviewer approved.
"""

from __future__ import annotations

import traceback

import pytest

from adaptive_disclosure_gateway.application.contracts import DisclosureStrategy
from adaptive_disclosure_gateway.application.ingestion import (
    IngestionError,
    ParsedDocument,
    normalize_text,
)
from adaptive_disclosure_gateway.application.presets import (
    CONTRACT_DOCUMENT_TYPE,
    DocumentAnalysisPresetError,
    list_document_presets,
    resolve_governance_preset,
)
from adaptive_disclosure_gateway.application.preview_confirmation import (
    PreviewConfirmationError,
)
from adaptive_disclosure_gateway.application.service import DisclosureApplicationService
from adaptive_disclosure_gateway.detection import Detector
from adaptive_disclosure_gateway.domain import SensitiveSpan, Treatment
from adaptive_disclosure_gateway.policies import PolicyRepository
from adaptive_disclosure_gateway.providers import FakeProvider
from adaptive_disclosure_gateway.task_analysis import (
    DeterministicTaskAnalyzer,
    TaskAnalysis,
    TaskRelevance,
)
from tests.api_support import HR_TEXT, POLICY_DIR, RecordingProvider, default_context
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
    provider=None, *, document_parser=None, detector=None, **context_overrides
) -> DisclosureApplicationService:
    return DisclosureApplicationService(
        policy_repository=PolicyRepository.from_directory(POLICY_DIR),
        provider=provider if provider is not None else FakeProvider(),
        default_context=default_context(**context_overrides),
        document_parser=document_parser,
        detector=detector,
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


# --- an uploaded document is executable only through the confirmed path ------
#
# The HTTP route calls ``execute_document``. Nothing but this guard stopped a
# second adapter -- a future MCP tool, a script, a refactor of the route --
# from calling the more obvious ``execute`` with a document request and
# reaching the provider with no reviewed preview behind it. Structural rather
# than conventional on purpose: the confirmation cannot be forgotten by a
# caller that does not know it exists.


def test_an_uploaded_document_cannot_be_executed_through_the_unconfirmed_method():
    provider = RecordingProvider()
    service = build_service(provider, document_parser=StubContractParser())
    request = service.build_document_request(
        filename="contract.pdf",
        file_bytes=b"%PDF-1.4 synthetic",
        task=CONTRACT_TASK,
        document_type=CONTRACT_DOCUMENT_TYPE,
    )

    with pytest.raises(PreviewConfirmationError):
        service.execute(request)

    assert provider.received == []


def test_the_historical_text_surface_is_untouched_by_the_confirmation_requirement():
    """``/disclosure/*`` and the CLI build requests with no document
    descriptor, and must keep executing without one -- the confirmation is a
    property of the structured-document surface, not a new global gate.
    """
    provider = RecordingProvider()
    service = build_service(provider)
    # HR content under the service's own HR default context: the point is
    # that `execute` still runs, not what the Contracts policy would say
    # about a contract analysed as an HR record.
    request = service.build_application_request(
        text=HR_TEXT, task="Summarize the team composition."
    )

    execution = service.execute(request)

    assert execution.provider.called is True
    assert len(provider.received) == 1


def test_a_document_request_records_the_resolved_analysis_mode_not_the_caller_s_none():
    """The confirmation binds the analysis mode. If ``None`` were recorded
    verbatim, a preview that accepted the default and an execute that named
    that same default explicitly would be two different states, and the
    approval would break for a client doing nothing wrong.
    """
    service = build_service(document_parser=StubContractParser())
    kwargs = {
        "filename": "contract.pdf",
        "file_bytes": b"%PDF-1.4 synthetic",
        "task": CONTRACT_TASK,
        "document_type": CONTRACT_DOCUMENT_TYPE,
    }

    defaulted = service.build_document_request(**kwargs)
    explicit = service.build_document_request(**kwargs, analysis_mode="contract_summary")

    assert defaulted.document == explicit.document
    assert defaulted.document.analysis_mode == "contract_summary"
    assert defaulted.document.document_type == CONTRACT_DOCUMENT_TYPE


def test_a_confirmed_document_execute_reaches_the_provider_through_the_application_layer():
    """The application-layer happy path, independent of HTTP: preview,
    confirm, execute -- one provider call, carrying the reviewed payload.
    """
    provider = RecordingProvider()
    service = build_service(provider, document_parser=StubContractParser())
    request = service.build_document_request(
        filename="contract.pdf",
        file_bytes=b"%PDF-1.4 synthetic",
        task=CONTRACT_TASK,
        document_type=CONTRACT_DOCUMENT_TYPE,
    )

    reviewed = service.preview_document(request)
    execution = service.execute_document(request, confirmation_token=reviewed.confirmation_token)

    assert len(provider.received) == 1
    assert provider.received[0].payload == reviewed.preview.external_payload
    assert execution.provider.called is True
    assert CONTRACTING_PARTY not in provider.received[0].payload


# --- the decision the confirmation authenticates is the decision executed ----
#
# Review round 2. The confirmation authenticated a decision and then the
# provider was handed a *second*, freshly recomputed one; the two were only
# expected to agree. ``Detector`` and ``TaskAnalyzer`` are replaceable
# injections, so "they agree" was a property of the components wired in on
# the day, not of the architecture. A stateful one is enough to make the
# approved payload and the transmitted payload differ -- which is exactly
# the demo's central guarantee failing.


class DecidesDifferentlyTheSecondTime:
    """A detector that reports nothing the second time it is asked about the
    same document, so a second decision over it discloses it raw.

    Every other input -- notably the pipeline's fail-closed pass over
    ``request.task`` -- is delegated to the real ``Detector`` and counted
    separately, so a decision about the document is never conflated with a
    detection over the task.
    """

    def __init__(self, document_text: str) -> None:
        self._document_text = document_text
        self._real = Detector()
        self.document_detection_calls = 0
        self.task_detection_calls = 0

    def start_counting_document_decisions(self) -> None:
        self.document_detection_calls = 0

    def detect(self, text: str) -> list[SensitiveSpan]:
        if text != self._document_text:
            self.task_detection_calls += 1
            return self._real.detect(text)
        self.document_detection_calls += 1
        if self.document_detection_calls > 1:
            return []
        return self._real.detect(text)


class BecomesPermissiveTheSecondTime:
    """A task analyzer whose second judgement asks for every category's exact
    original value -- the most disclosing answer B3/B4 can act on.

    The second replaceable injection in the decision phase, independent of
    the detector: if the decision were recomputed after the confirmation was
    verified, this alone would change what is transmitted.
    """

    def __init__(self) -> None:
        self._real = DeterministicTaskAnalyzer()
        self.analyze_calls = 0

    def start_counting_analyses(self) -> None:
        self.analyze_calls = 0

    def analyze(self, task: str, categories) -> TaskAnalysis:
        self.analyze_calls += 1
        if self.analyze_calls > 1:
            return TaskAnalysis(
                relevance_by_category={
                    category: TaskRelevance.RELEVANT_WITH_EXACT_VALUE for category in categories
                }
            )
        return self._real.analyze(task, categories)


def _contract_request(service):
    return service.build_document_request(
        filename="contract.pdf",
        file_bytes=b"%PDF-1.4 synthetic",
        task=CONTRACT_TASK,
        document_type=CONTRACT_DOCUMENT_TYPE,
    )


def _normalized_contract_text() -> str:
    """The document text the decision phase actually sees, i.e. after the
    ingestion boundary normalized what the parser returned. Read from the
    real boundary rather than hardcoded, so a normalization change cannot
    quietly turn the stateful detector below into a no-op.
    """
    return normalize_text(CONTRACTS_FIXTURE).text


def test_execute_document_sends_the_exact_decision_authenticated_by_the_preview_confirmation():
    """The guarantee, stated as a test: the provider receives the payload the
    confirmation authenticated -- not a payload recomputed after it.

    The detector decides differently the second time it is asked about this
    document. An ``execute_document`` that verifies one decision and then
    recomputes another would verify the safe payload and transmit the raw
    contract; there is no assertion about component determinism here,
    because the property must not depend on it.
    """
    provider = RecordingProvider()
    detector = DecidesDifferentlyTheSecondTime(_normalized_contract_text())
    service = build_service(provider, document_parser=StubContractParser(), detector=detector)
    request = _contract_request(service)

    reviewed = service.preview_document(request)
    detector.start_counting_document_decisions()
    execution = service.execute_document(request, confirmation_token=reviewed.confirmation_token)

    assert detector.document_detection_calls == 1, (
        "the document decision phase ran more than once inside execute_document -- "
        "whichever decision was executed was not the one the confirmation authenticated"
    )
    assert len(provider.received) == 1
    assert provider.received[0].payload == reviewed.preview.external_payload
    assert provider.received[0].task == request.task
    assert CONTRACTING_PARTY not in provider.received[0].payload
    assert execution.summary.status == reviewed.preview.summary.status


def test_execute_document_is_unaffected_by_a_task_analyzer_that_would_decide_differently():
    """The same property through the other replaceable injection: a second
    task analysis that asks for every exact original value must never be the
    one that shapes what is transmitted.
    """
    provider = RecordingProvider()
    analyzer = BecomesPermissiveTheSecondTime()
    service = DisclosureApplicationService(
        policy_repository=PolicyRepository.from_directory(POLICY_DIR),
        provider=provider,
        default_context=default_context(),
        document_parser=StubContractParser(),
        task_analyzer=analyzer,
    )
    request = _contract_request(service)

    reviewed = service.preview_document(request)
    analyzer.start_counting_analyses()
    service.execute_document(request, confirmation_token=reviewed.confirmation_token)

    assert analyzer.analyze_calls == 1
    assert len(provider.received) == 1
    assert provider.received[0].payload == reviewed.preview.external_payload
    assert CONTRACTING_PARTY not in provider.received[0].payload


def test_execute_document_runs_the_document_decision_phase_exactly_once():
    """Counted against the real detector, with no stateful behaviour at all:
    one decision about the document per ``execute_document`` call. Two would
    mean the verified decision and the executed one are different objects,
    however much they happen to agree.
    """
    provider = RecordingProvider()
    detector = DecidesDifferentlyTheSecondTime(_normalized_contract_text())
    service = build_service(provider, document_parser=StubContractParser(), detector=detector)
    request = _contract_request(service)

    reviewed = service.preview_document(request)
    assert detector.document_detection_calls == 1
    detector.start_counting_document_decisions()

    service.execute_document(request, confirmation_token=reviewed.confirmation_token)

    assert detector.document_detection_calls == 1
