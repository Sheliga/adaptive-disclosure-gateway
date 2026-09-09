"""T20 / issue #28, slice 1: ``application/service.py``'s
``DisclosureApplicationService`` -- the use-case boundary wiring ingestion,
the shared decision phase and the real pipeline together for a future
adapter. Assertions here run the real core (real detector, real treatments,
real policies) end to end; only the provider is a local stub, exactly like
``tests/test_pipeline.py``'s own style.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from adaptive_disclosure_gateway.application.contracts import (
    DisclosureApplicationRequest,
    DisclosureStrategy,
    GovernanceOverrides,
)
from adaptive_disclosure_gateway.application.examples import ExampleNotFoundError
from adaptive_disclosure_gateway.application.ingestion import IngestionError, normalize_text
from adaptive_disclosure_gateway.application.requests import ContentSourceError, MissingTaskError
from adaptive_disclosure_gateway.application.service import DisclosureApplicationService
from adaptive_disclosure_gateway.detection import Detector
from adaptive_disclosure_gateway.domain import GovernanceContext, SensitiveSpan, Treatment
from adaptive_disclosure_gateway.policies import PolicyRepository
from adaptive_disclosure_gateway.providers import (
    FakeProvider,
    ProviderRequest,
    ProviderResponse,
    count_transmitted_bytes,
)

POLICY_DIR = Path(__file__).parents[1] / "configs" / "policies"
EXAMPLES_DIR = Path(__file__).parents[1] / "corpus" / "hr" / "v1" / "cases"

HR_TEXT = "Employee: Ana Souza\nCPF: 123.456.789-09\nSalary: R$ 8500.00\nDepartment: Engineering\n"
HR_TEXT_WITH_MEDICAL = HR_TEXT + "Medical notes: Reports chronic migraine.\n"


def _policy_repo() -> PolicyRepository:
    return PolicyRepository.from_directory(POLICY_DIR)


def _default_context(**overrides) -> GovernanceContext:
    values = {
        "domain": "hr",
        "purpose": "team_summary",
        "policy_version": "hr-v1",
        "provider_class": "fake",
        "requester_role": "hr_analyst",
        "session_id": "demo-session",
    }
    values.update(overrides)
    return GovernanceContext(**values)


@dataclass
class RecordingProvider:
    provider_class: str = "fake"
    received: list[ProviderRequest] = field(default_factory=list)

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.received.append(request)
        return ProviderResponse(
            text=f"ack over {len(request.payload)} chars",
            model_id="stub-model",
            model_snapshot="stub-snapshot",
            decoding_config={},
            transmitted_bytes=count_transmitted_bytes(request.payload),
        )


@dataclass
class EchoingRecordingProvider:
    provider_class: str = "fake"
    received: list[ProviderRequest] = field(default_factory=list)

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.received.append(request)
        return ProviderResponse(
            text=f"Summary acknowledged: {request.payload}",
            model_id="stub-model",
            model_snapshot="stub-snapshot",
            decoding_config={},
            transmitted_bytes=count_transmitted_bytes(request.payload),
        )


@dataclass
class NeverCallMeProvider:
    """A provider whose generate() must never be invoked. Used to prove
    preview() never reaches the provider boundary at all."""

    provider_class: str = "fake"

    def generate(self, request: ProviderRequest) -> ProviderResponse:  # pragma: no cover
        raise AssertionError("preview() must never call the provider")


def _service(
    provider, *, examples_directory: Path | None = None, **context_overrides
) -> DisclosureApplicationService:
    return DisclosureApplicationService(
        policy_repository=_policy_repo(),
        provider=provider,
        default_context=_default_context(**context_overrides),
        examples_directory=examples_directory,
    )


def _app_request(
    text: str,
    task: str = "summarize personnel record",
    strategy=DisclosureStrategy.RECOMMENDED,
    **gov,
) -> DisclosureApplicationRequest:
    return DisclosureApplicationRequest(
        content=normalize_text(text),
        task=task,
        strategy=strategy,
        governance=GovernanceOverrides(**gov),
    )


# --- 1. preview never calls the provider ------------------------------------


def test_preview_never_calls_the_provider():
    service = _service(NeverCallMeProvider())
    request = _app_request(HR_TEXT)

    preview = service.preview(request)

    assert preview.summary.status == "allowed"


# --- 2. preview and execute share one decision path -------------------------


def test_preview_and_execute_agree_on_external_payload_and_summary():
    provider = RecordingProvider()
    service = _service(provider)
    request = _app_request(HR_TEXT)

    preview = service.preview(request)
    execution = service.execute(request)

    assert provider.received, "expected execute() to have called the provider"
    assert preview.external_payload == provider.received[-1].payload
    assert preview.summary == execution.summary
    assert preview.treatment == execution.treatment


# --- 3. no leak in any result contract, fully serialized --------------------


def test_no_result_contract_contains_raw_values_or_pseudonym_mapping():
    provider = RecordingProvider()
    service = _service(provider)
    request = _app_request(HR_TEXT)

    preview = service.preview(request)
    execution = service.execute(request)

    pseudonym = next(c for c in preview.summary.categories if c.category == "employee_name")
    # occurrence_count/action are safe metadata -- the pseudonym *string*
    # itself only ever lives in external_payload, which is fine (see
    # contracts.py's module docstring); what must never appear anywhere is
    # the ORIGINAL value or a mapping tying it to its pseudonym.
    assert pseudonym.category == "employee_name"

    dumped_preview = str(dataclasses.asdict(preview))
    dumped_execution = str(dataclasses.asdict(execution))
    for dumped in (dumped_preview, dumped_execution):
        assert "Ana Souza" not in dumped
        assert "123.456.789-09" not in dumped
        assert "Ana Souza:" not in dumped  # a mapping-shaped string


def test_no_result_contract_leaks_lifecycle_identifiers_from_governance_overrides():
    provider = RecordingProvider()
    service = _service(provider)
    request = _app_request(
        HR_TEXT,
        requester_id="secret-requester-id",
        session_id="secret-session-id",
        document_id="secret-document-id",
        request_id="secret-request-id",
    )

    preview = service.preview(request)
    execution = service.execute(request)

    for dumped in (str(dataclasses.asdict(preview)), str(dataclasses.asdict(execution))):
        assert "secret-requester-id" not in dumped
        assert "secret-session-id" not in dumped
        assert "secret-document-id" not in dumped
        assert "secret-request-id" not in dumped


# --- 4. execute calls the provider exactly once for an allowed request ------


def test_execute_calls_the_provider_exactly_once_for_an_allowed_request():
    provider = RecordingProvider()
    service = _service(provider)
    request = _app_request(HR_TEXT)

    service.execute(request)

    assert len(provider.received) == 1


# --- 5. a blocked request never reaches the provider -------------------------


def test_blocked_request_never_reaches_the_provider_and_execute_returns_a_safe_result():
    provider = RecordingProvider()
    service = _service(provider)
    request = _app_request(HR_TEXT_WITH_MEDICAL)

    execution = service.execute(request)

    assert provider.received == []
    assert execution.summary.status == "blocked"
    assert execution.provider.called is False
    assert execution.final_answer is None


def test_blocked_request_also_never_reaches_the_provider_in_preview():
    provider = RecordingProvider()
    service = _service(provider)
    request = _app_request(HR_TEXT_WITH_MEDICAL)

    preview = service.preview(request)

    assert provider.received == []
    assert preview.summary.status == "blocked"
    assert preview.external_payload == ""


# --- 6. reconstruction happens where supported and final_answer reflects it -


def test_reconstruction_happens_and_final_answer_reflects_it():
    provider = EchoingRecordingProvider()
    service = _service(provider)
    text = "Employee: Ana Souza\n"
    request = _app_request(
        text, strategy=DisclosureStrategy.REVERSIBLE_PSEUDONYMIZATION, session_id="demo-session"
    )

    execution = service.execute(request)

    assert execution.reconstruction.attempted is True
    assert execution.reconstruction.changed_from_provider_response is True
    assert execution.final_answer == f"Summary acknowledged: {text}"
    assert "Ana Souza" in execution.final_answer
    assert "PSEUDO-" not in execution.final_answer


# --- 7. FakeProvider works end-to-end ----------------------------------------


def test_fake_provider_works_end_to_end_through_the_service():
    service = _service(FakeProvider())
    request = _app_request(HR_TEXT)

    execution = service.execute(request)

    assert execution.provider.called is True
    assert execution.provider.failed is False
    assert execution.final_answer is not None


# --- 9. direct text reaches the core unchanged (through the ingestion +
# service boundary) -----------------------------------------------------------


def test_direct_text_reaches_the_core_unchanged_under_the_direct_strategy():
    provider = RecordingProvider()
    service = _service(provider)
    text = "Employee: Ana Souza\nCPF: 123.456.789-09\n"
    request = _app_request(text, strategy=DisclosureStrategy.DIRECT)

    preview = service.preview(request)

    # B0 -- Direct sends the text through completely unchanged; this proves
    # the ingestion boundary did not mutate it before the core ever saw it.
    assert preview.external_payload == text


# --- governance override merging --------------------------------------------


def test_governance_overrides_merge_onto_the_default_context_ignoring_none_fields():
    provider = RecordingProvider()
    service = _service(provider)
    request = _app_request(HR_TEXT, purpose="salary_analysis")

    preview = service.preview(request)

    assert preview.governance.purpose == "salary_analysis"
    assert preview.governance.domain == "hr"
    assert preview.governance.policy_version == "hr-v1"


def test_safe_governance_view_never_exposes_requester_id_or_lifecycle_identifiers():
    provider = RecordingProvider()
    service = _service(provider)
    request = _app_request(HR_TEXT, requester_id="secret-id", session_id="secret-session")

    preview = service.preview(request)

    view_fields = {f.name for f in dataclasses.fields(preview.governance)}
    assert "requester_id" not in view_fields
    assert "session_id" not in view_fields


@dataclass
class CountingDetector:
    """Wraps the real ``Detector`` and counts how many times ``detect`` was
    actually called. Not a fake detector: every call is delegated to the
    real one, so the service under test still runs real detection.
    """

    wrapped: Detector = field(default_factory=Detector)
    calls: int = 0

    def detect(self, text: str) -> list[SensitiveSpan]:
        self.calls += 1
        return self.wrapped.detect(text)


def test_execute_runs_the_decision_phase_exactly_once():
    """``execute`` must build its summary from the decision the run that
    actually contacted the provider made -- not from a second, standalone
    ``decide_disclosure`` call whose agreement with the real one is only
    argued, never guaranteed.

    Pinned by counting real ``Detector.detect`` calls. ``run_disclosure_case``
    itself calls ``detect`` twice for a non-B0 treatment (once over
    ``request.text``, once for the fail-closed check over ``request.task``),
    so exactly one decision phase means exactly two calls. A regression that
    reintroduced a separate summary-only decision pass would make it four.
    """
    detector = CountingDetector()
    provider = RecordingProvider()
    service = DisclosureApplicationService(
        policy_repository=_policy_repo(),
        provider=provider,
        default_context=_default_context(),
        detector=detector,
    )

    result = service.execute(_app_request(HR_TEXT))

    assert result.summary.status == "allowed"
    assert detector.calls == 2


def test_execute_summary_describes_the_run_that_actually_reached_the_provider():
    """The categories/status ``execute`` reports must come from the same
    ``DisclosureResult`` whose ``external_payload`` was handed to the
    provider -- proven by comparing against the payload the provider
    actually received.
    """
    provider = RecordingProvider()
    service = _service(provider)

    result = service.execute(_app_request(HR_TEXT))

    assert len(provider.received) == 1
    sent_payload = provider.received[0].payload
    preview = service.preview(_app_request(HR_TEXT))

    assert preview.external_payload == sent_payload
    assert result.summary == preview.summary


# --- describe_health / list_strategies (T20 / issue #28, slice 2) -----------


def test_describe_health_reports_fake_provider_as_deterministic_demo_mode():
    service = _service(FakeProvider())

    health = service.describe_health()

    assert health.provider_class == "fake"
    assert health.model_id == FakeProvider.model_id
    assert health.model_snapshot == FakeProvider.model_snapshot
    assert health.deterministic_demo_mode is True
    assert set(health.treatments_available) == set(Treatment)


def test_describe_health_reports_false_for_a_non_fake_provider():
    service = _service(RecordingProvider())

    health = service.describe_health()

    assert health.deterministic_demo_mode is False


def test_describe_health_never_calls_the_provider():
    service = _service(NeverCallMeProvider())

    service.describe_health()  # must not raise -- generate() would assert


def test_list_strategies_covers_every_treatment_with_one_recommended():
    service = _service(FakeProvider())

    options = service.list_strategies()

    assert {option.treatment for option in options} == set(Treatment)
    assert sum(option.recommended for option in options) == 1


# --- build_application_request (T20 / issue #28, slice 2) -------------------


def test_build_application_request_from_direct_text():
    service = _service(FakeProvider())

    request = service.build_application_request(text=HR_TEXT, task="summarize")

    assert request.content.text == HR_TEXT
    assert request.content.source_kind == "direct_text"
    assert request.task == "summarize"
    assert request.strategy == DisclosureStrategy.RECOMMENDED


def test_build_application_request_from_a_file():
    service = _service(FakeProvider())

    request = service.build_application_request(
        filename="record.txt", file_bytes=HR_TEXT.encode("utf-8"), task="summarize"
    )

    assert request.content.text == HR_TEXT
    assert request.content.source_kind == "text_file"
    assert request.content.source_name == "record.txt"


def test_build_application_request_from_an_example_uses_the_examples_directory():
    service = _service(FakeProvider(), examples_directory=EXAMPLES_DIR)

    request = service.build_application_request(example_id="hr_team_summary_001")

    assert "Renata Farias" in request.content.text
    assert request.task  # the example's own task was used
    assert request.governance.domain == "hr"


def test_build_application_request_caller_task_wins_over_the_example_task():
    service = _service(FakeProvider(), examples_directory=EXAMPLES_DIR)

    request = service.build_application_request(
        example_id="hr_team_summary_001", task="a different task"
    )

    assert request.task == "a different task"


def test_build_application_request_caller_governance_wins_over_the_example_governance():
    service = _service(FakeProvider(), examples_directory=EXAMPLES_DIR)

    request = service.build_application_request(
        example_id="hr_team_summary_001",
        governance=GovernanceOverrides(purpose="salary_analysis"),
    )

    assert request.governance.purpose == "salary_analysis"
    assert request.governance.domain == "hr"


def test_build_application_request_rejects_an_unknown_example_id():
    service = _service(FakeProvider(), examples_directory=EXAMPLES_DIR)

    with pytest.raises(ExampleNotFoundError):
        service.build_application_request(example_id="does_not_exist")


def test_build_application_request_rejects_no_content_source():
    service = _service(FakeProvider())

    with pytest.raises(ContentSourceError):
        service.build_application_request(task="summarize")


def test_build_application_request_rejects_more_than_one_content_source():
    service = _service(FakeProvider())

    with pytest.raises(ContentSourceError):
        service.build_application_request(text=HR_TEXT, example_id="hr_team_summary_001")


def test_build_application_request_error_names_sources_never_content():
    service = _service(FakeProvider())

    with pytest.raises(ContentSourceError) as excinfo:
        service.build_application_request(text=HR_TEXT, example_id="hr_team_summary_001")

    message = str(excinfo.value)
    assert "Ana Souza" not in message
    assert "123.456.789-09" not in message


def test_build_application_request_rejects_incomplete_file_source():
    service = _service(FakeProvider())

    with pytest.raises(ContentSourceError):
        service.build_application_request(filename="record.txt")


def test_build_application_request_rejects_missing_task_for_direct_text():
    service = _service(FakeProvider())

    with pytest.raises(MissingTaskError):
        service.build_application_request(text=HR_TEXT)


def test_build_application_request_rejects_missing_task_for_a_file():
    service = _service(FakeProvider())

    with pytest.raises(MissingTaskError):
        service.build_application_request(filename="record.txt", file_bytes=HR_TEXT.encode())


def test_build_application_request_propagates_ingestion_errors():
    service = _service(FakeProvider())

    with pytest.raises(IngestionError):
        service.build_application_request(text="   ", task="summarize")


CORPUS_DIR = Path(__file__).parents[1] / "corpus" / "hr" / "v1" / "cases"


def test_a_prepared_example_actually_reaches_the_configured_provider():
    """The guided flow's default path -- pick a prepared example, execute --
    must genuinely reach the provider the deployer configured.

    A prepared example is a *scenario* (domain, purpose, policy version,
    requester role); the provider class is a *deployment* fact owned by the
    server that configured the provider. Letting an example's own
    ``provider_class`` override the deployer's turned every example-sourced
    execution into a fail-closed ``ProviderClassMismatchError``: allowed by
    the treatment, then rejected at the provider boundary because the
    corpus case names ``external_llm`` while the configured demo provider
    declares something else. The whole advisor demo silently produced
    ``final_answer=None`` for every prepared example.

    This pins the flow end to end rather than the field list, so it fails
    for the real defect (no answer reaches the user) rather than for a
    naming choice.
    """
    provider = RecordingProvider()
    service = DisclosureApplicationService(
        policy_repository=_policy_repo(),
        provider=provider,
        default_context=_default_context(),
        examples_directory=CORPUS_DIR,
    )
    example_id = service.list_examples()[0].example_id

    result = service.execute(service.build_application_request(example_id=example_id))

    assert result.summary.status == "allowed"
    assert result.provider.called is True
    assert result.provider.failed is False
    assert len(provider.received) == 1
    assert result.final_answer is not None


def test_an_explicit_caller_override_of_provider_class_still_fails_closed_on_mismatch():
    """Excluding ``provider_class`` from an example's defaults must not
    weaken the provider-class check itself: an explicit caller override that
    disagrees with the configured provider must still be rejected before
    ``generate`` is ever called.
    """
    provider = RecordingProvider()
    service = DisclosureApplicationService(
        policy_repository=_policy_repo(),
        provider=provider,
        default_context=_default_context(),
        examples_directory=CORPUS_DIR,
    )
    example_id = service.list_examples()[0].example_id

    result = service.execute(
        service.build_application_request(
            example_id=example_id,
            governance=GovernanceOverrides(provider_class="external_llm"),
        )
    )

    assert result.provider.called is False
    assert result.provider.failure_kind == "ProviderClassMismatchError"
    assert provider.received == []
