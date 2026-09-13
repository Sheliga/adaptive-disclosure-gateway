"""T26 / issue #67: ``DisclosureApplicationService.export``/``.restore`` --
the application-layer use case for exporting a disclosed representation
together with a sealed restore handle, and later restoring pseudonyms from
arbitrary submitted text through that handle alone.

Every test here targets a real defect this feature could plausibly have:
export producing a payload that disagrees with preview's own payload for the
identical input, a BLOCKed decision still producing an export, B0/B1
producing spurious restorable entries, one document's handle reconstructing
another document's pseudonyms (a cross-scope oracle), the feature failing
open instead of closed when no secret is configured, and any of it leaking
through an exception message or a span attribute.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from adaptive_disclosure_gateway.application.contracts import (
    DisclosureApplicationRequest,
    DisclosureStrategy,
    ExportRefusedError,
    GovernanceOverrides,
)
from adaptive_disclosure_gateway.application.ingestion import normalize_text
from adaptive_disclosure_gateway.application.restore_handle import (
    RestoreHandleSealer,
    RestoreUnavailableError,
)
from adaptive_disclosure_gateway.application.service import DisclosureApplicationService
from adaptive_disclosure_gateway.domain import GovernanceContext, PseudonymScope, Treatment
from adaptive_disclosure_gateway.policies import PolicyRepository
from adaptive_disclosure_gateway.providers import ProviderRequest, ProviderResponse
from tests import telemetry_assertions

POLICY_DIR = Path(__file__).parents[1] / "configs" / "policies"

HR_TEXT = "Employee: Ana Souza\nCPF: 123.456.789-09\nSalary: R$ 8500.00\nDepartment: Engineering\n"
HR_TEXT_WITH_MEDICAL = HR_TEXT + "Medical notes: Reports chronic migraine.\n"

SECRET = "restore-handle-test-secret-material-32bytes!!"


@dataclass
class NeverCallMeProvider:
    provider_class: str = "fake"

    def generate(self, request: ProviderRequest) -> ProviderResponse:  # pragma: no cover
        raise AssertionError("export must never call the provider")


def _context(**overrides) -> GovernanceContext:
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


def _service(sealer=None, provider=None, **context_overrides) -> DisclosureApplicationService:
    return DisclosureApplicationService(
        policy_repository=PolicyRepository.from_directory(POLICY_DIR),
        provider=provider if provider is not None else NeverCallMeProvider(),
        default_context=_context(**context_overrides),
        restore_handle_sealer=sealer,
    )


def _request(text: str, strategy: DisclosureStrategy, task: str = "summarize", **gov_overrides):
    return DisclosureApplicationRequest(
        content=normalize_text(text),
        task=task,
        strategy=strategy,
        governance=GovernanceOverrides(**gov_overrides),
    )


def _configured_sealer(secret: str = SECRET, **kwargs) -> RestoreHandleSealer:
    return RestoreHandleSealer(secret=secret, **kwargs)


# --- export/preview agreement --------------------------------------------------


def test_export_external_payload_matches_preview_for_the_same_request():
    service = _service(sealer=_configured_sealer())
    request = _request(HR_TEXT, DisclosureStrategy.REVERSIBLE_PSEUDONYMIZATION)

    export = service.export(request)
    preview = service.preview(request)

    assert export.external_payload == preview.external_payload
    assert export.treatment is Treatment.REVERSIBLE_PSEUDONYMIZATION
    assert export.strategy is DisclosureStrategy.REVERSIBLE_PSEUDONYMIZATION


def test_export_never_calls_the_provider():
    # NeverCallMeProvider raises if .generate is ever invoked -- constructing
    # the service with it and succeeding at export is the proof.
    service = _service(sealer=_configured_sealer())
    request = _request(HR_TEXT, DisclosureStrategy.REVERSIBLE_PSEUDONYMIZATION)

    service.export(request)  # would raise AssertionError if it called the provider


# --- restorable_count per treatment --------------------------------------------


def test_b2_export_restorable_count_matches_the_number_of_pseudonymized_entries():
    service = _service(sealer=_configured_sealer())
    request = _request(HR_TEXT, DisclosureStrategy.REVERSIBLE_PSEUDONYMIZATION)

    export = service.export(request)

    # HR_TEXT pseudonymizes employee_name and cpf (see reversible_pseudonymization.ACTIONS).
    assert export.restorable_count == 2


def test_b0_direct_export_has_zero_restorable_entries_and_unchanged_payload():
    service = _service(sealer=_configured_sealer())
    request = _request(HR_TEXT, DisclosureStrategy.DIRECT)

    export = service.export(request)

    assert export.restorable_count == 0
    assert export.external_payload == HR_TEXT


def test_b1_static_sanitization_export_has_zero_restorable_entries():
    service = _service(sealer=_configured_sealer())
    request = _request(HR_TEXT, DisclosureStrategy.STATIC_SANITIZATION)

    export = service.export(request)

    assert export.restorable_count == 0


# --- BLOCK_REQUEST refuses export -----------------------------------------------


def test_a_blocked_decision_refuses_export():
    service = _service(sealer=_configured_sealer())
    # medical_data is BLOCK_REQUEST under every treatment's static mapping.
    request = _request(HR_TEXT_WITH_MEDICAL, DisclosureStrategy.REVERSIBLE_PSEUDONYMIZATION)

    with pytest.raises(ExportRefusedError):
        service.export(request)


def test_export_refused_error_names_no_document_content():
    service = _service(sealer=_configured_sealer())
    request = _request(HR_TEXT_WITH_MEDICAL, DisclosureStrategy.REVERSIBLE_PSEUDONYMIZATION)

    with pytest.raises(ExportRefusedError) as excinfo:
        service.export(request)

    message = str(excinfo.value)
    assert "chronic migraine" not in message
    assert "Ana Souza" not in message


# --- round trip through export -> restore ---------------------------------------


def test_export_then_restore_recovers_the_originals_from_the_disclosed_text():
    service = _service(sealer=_configured_sealer())
    request = _request(HR_TEXT, DisclosureStrategy.REVERSIBLE_PSEUDONYMIZATION)

    export = service.export(request)
    restored = service.restore(text=export.external_payload, restore_handle=export.restore_handle)

    assert "Ana Souza" in restored.restored_text
    assert "123.456.789-09" in restored.restored_text
    assert restored.restored_count == 2
    assert restored.unresolved_count == 0


def test_a_handle_from_one_document_does_not_restore_a_different_documents_pseudonyms():
    sealer = _configured_sealer()
    service = _service(sealer=sealer)

    request_a = _request(
        HR_TEXT, DisclosureStrategy.REVERSIBLE_PSEUDONYMIZATION, document_id="doc-a"
    )
    request_b = _request(
        "Employee: Bruno Lima\nCPF: 987.654.321-00\nDepartment: Sales\n",
        DisclosureStrategy.REVERSIBLE_PSEUDONYMIZATION,
        requested_pseudonym_scope=PseudonymScope.DOCUMENT,
        document_id="doc-b",
    )

    export_a = service.export(request_a)
    export_b = service.export(request_b)

    # Apply document A's handle to document B's disclosed text: B's own
    # pseudonyms must survive untouched, and nothing from A leaks in.
    restored = service.restore(
        text=export_b.external_payload, restore_handle=export_a.restore_handle
    )

    assert "Bruno Lima" not in restored.restored_text
    assert restored.restored_count == 0
    assert restored.unresolved_count > 0


def test_restore_never_reveals_a_pseudonym_absent_from_the_submitted_text():
    service = _service(sealer=_configured_sealer())
    request = _request(HR_TEXT, DisclosureStrategy.REVERSIBLE_PSEUDONYMIZATION)
    export = service.export(request)

    restored = service.restore(
        text="no pseudonyms in this text at all", restore_handle=export.restore_handle
    )

    assert restored.restored_text == "no pseudonyms in this text at all"
    assert restored.restored_count == 0
    assert restored.unresolved_count == 0


# --- fail closed with no secret configured (D2) ---------------------------------


def test_export_fails_closed_when_no_restore_handle_secret_is_configured():
    service = _service(sealer=None)  # defaults to an unconfigured sealer
    request = _request(HR_TEXT, DisclosureStrategy.REVERSIBLE_PSEUDONYMIZATION)

    with pytest.raises(RestoreUnavailableError):
        service.export(request)


def test_restore_fails_closed_when_no_restore_handle_secret_is_configured():
    service = _service(sealer=None)

    with pytest.raises(RestoreUnavailableError):
        service.restore(text="whatever", restore_handle="rh1.whatever")


def test_preview_still_works_when_no_restore_handle_secret_is_configured():
    service = _service(sealer=None)
    request = _request(HR_TEXT, DisclosureStrategy.REVERSIBLE_PSEUDONYMIZATION)

    preview = service.preview(request)  # must not raise
    assert preview.external_payload


# --- no-leak: telemetry ----------------------------------------------------------


def test_export_and_restore_span_attributes_never_leak_originals_or_pseudonyms(recorded_spans):
    service = _service(sealer=_configured_sealer())
    request = _request(HR_TEXT, DisclosureStrategy.REVERSIBLE_PSEUDONYMIZATION)

    export = service.export(request)
    recorded_spans.clear()
    service.restore(text=export.external_payload, restore_handle=export.restore_handle)

    finished = recorded_spans.get_finished_spans()
    telemetry_assertions.assert_span_attributes_never_leak(
        finished, "Ana Souza", "123.456.789-09", HR_TEXT, export.external_payload, SECRET
    )


def test_export_repr_style_objects_never_print_entries_or_secret():
    sealer = _configured_sealer()
    rendered = repr(sealer)
    assert SECRET not in rendered
    assert "Ana Souza" not in rendered
