"""T29 / issue #72: ``DisclosureApplicationService``'s wiring of the demo
vault explorer -- ``preview``/``preview_document`` setting
``DisclosurePreview.vault_explorer_token`` when
``demo_vault_explorer_enabled`` is set, and ``explore_vault`` resolving that
token against this service's own vault. Mirrors
``tests/test_application_service.py``'s T27 demo-transparency section in
style, and its adversarial cross-request isolation test.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from adaptive_disclosure_gateway.application.contracts import (
    DemoVaultExplorerDisabledError,
    DisclosureApplicationRequest,
    DisclosureStrategy,
    GovernanceOverrides,
)
from adaptive_disclosure_gateway.application.ingestion import normalize_text
from adaptive_disclosure_gateway.application.service import DisclosureApplicationService
from adaptive_disclosure_gateway.application.vault_explorer import VaultExplorerReferenceError
from adaptive_disclosure_gateway.domain import GovernanceContext, PseudonymScope
from adaptive_disclosure_gateway.policies import PolicyRepository
from adaptive_disclosure_gateway.providers import FakeProvider
from adaptive_disclosure_gateway.vault import InMemoryVault

POLICY_DIR = Path(__file__).parents[1] / "configs" / "policies"

HR_TEXT = "Employee: Ana Souza\nCPF: 123.456.789-09\nSalary: R$ 8500.00\nDepartment: Engineering\n"
OTHER_TEXT = "Employee: Carlos Lima\nCPF: 987.654.321-00\nDepartment: Finance\n"


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
class _SpyVault(InMemoryVault):
    reconstruct_calls: list[tuple] = field(default_factory=list)

    def reconstruct(self, scope, scope_key, pseudonym):
        self.reconstruct_calls.append((scope, scope_key, pseudonym))
        return super().reconstruct(scope, scope_key, pseudonym)


def _service(
    provider=None,
    *,
    demo_vault_explorer_enabled: bool = False,
    vault=None,
    **context_overrides,
) -> DisclosureApplicationService:
    return DisclosureApplicationService(
        policy_repository=_policy_repo(),
        provider=provider if provider is not None else FakeProvider(),
        vault=vault,
        default_context=_default_context(**context_overrides),
        demo_vault_explorer_enabled=demo_vault_explorer_enabled,
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


# --- flag off ------------------------------------------------------------------


def test_vault_explorer_token_is_none_when_flag_disabled():
    service = _service(demo_vault_explorer_enabled=False)

    preview = service.preview(
        _app_request(HR_TEXT, strategy=DisclosureStrategy.REVERSIBLE_PSEUDONYMIZATION)
    )

    assert preview.vault_explorer_token is None


def test_explore_vault_raises_when_flag_disabled_without_touching_the_vault():
    vault = _SpyVault()
    service = _service(demo_vault_explorer_enabled=False, vault=vault)

    with pytest.raises(DemoVaultExplorerDisabledError):
        service.explore_vault("vx1.anything")

    assert vault.reconstruct_calls == []


# --- flag on: B2 reversible pseudonymization -----------------------------------


def test_vault_explorer_token_round_trips_pseudonymize_entries_for_b2():
    service = _service(demo_vault_explorer_enabled=True)

    preview = service.preview(
        _app_request(HR_TEXT, strategy=DisclosureStrategy.REVERSIBLE_PSEUDONYMIZATION)
    )

    assert preview.vault_explorer_token is not None
    view = service.explore_vault(preview.vault_explorer_token)
    assert view.scope == "session"
    categories = {entry.category for entry in view.entries}
    assert "employee_name" in categories
    employee_entry = next(e for e in view.entries if e.category == "employee_name")
    assert employee_entry.original == "Ana Souza"
    assert employee_entry.present is True
    assert employee_entry.pseudonym.startswith("PSEUDO-employee_name-")

    # GENERALIZE (salary) and PRESERVE (department) under B2's static
    # per-category map must never appear as entries -- only PSEUDONYMIZE.
    assert "salary" not in categories
    assert "department" not in categories


def test_vault_explorer_token_has_null_scope_for_b1_static_sanitization():
    service = _service(demo_vault_explorer_enabled=True)

    preview = service.preview(
        _app_request(HR_TEXT, strategy=DisclosureStrategy.STATIC_SANITIZATION)
    )

    assert preview.vault_explorer_token is not None
    view = service.explore_vault(preview.vault_explorer_token)
    assert view.scope is None
    assert view.entries == ()


def test_vault_explorer_token_has_null_scope_for_b0_direct():
    service = _service(demo_vault_explorer_enabled=True)

    preview = service.preview(_app_request(HR_TEXT, strategy=DisclosureStrategy.DIRECT))

    assert preview.vault_explorer_token is not None
    view = service.explore_vault(preview.vault_explorer_token)
    assert view.scope is None
    assert view.entries == ()


def test_blocked_decision_never_issues_a_vault_explorer_token():
    """medical_data is `block_request` under hr-v1 -- including it forces a
    blocked decision regardless of strategy.
    """
    service = _service(demo_vault_explorer_enabled=True)
    text = HR_TEXT + "Medical notes: Reports chronic migraine.\n"

    preview = service.preview(
        _app_request(text, strategy=DisclosureStrategy.REVERSIBLE_PSEUDONYMIZATION)
    )

    assert preview.summary.status == "blocked"
    assert preview.vault_explorer_token is None


def test_organization_scope_never_issues_a_vault_explorer_token():
    """hr_admin's role ceiling is 'organization' (configs/policies/hr-v1.yaml)
    -- requesting ORGANIZATION scope explicitly as hr_admin resolves to it,
    and issuance must refuse for that scope.
    """
    service = _service(demo_vault_explorer_enabled=True, requester_role="hr_admin")

    preview = service.preview(
        _app_request(
            HR_TEXT,
            strategy=DisclosureStrategy.REVERSIBLE_PSEUDONYMIZATION,
            requested_pseudonym_scope=PseudonymScope.ORGANIZATION,
        )
    )

    assert preview.vault_explorer_token is None


def test_preview_document_inherits_the_vault_explorer_token():
    from adaptive_disclosure_gateway.application.ingestion import ParsedDocument
    from adaptive_disclosure_gateway.application.presets import CONTRACT_DOCUMENT_TYPE
    from tests.contracts_fixture import CONTRACTS_FIXTURE

    class _StubDocumentParser:
        parser_name = "stub_document_parser"
        parser_version = "test"

        def parse(self, *, safe_name: str, data: bytes) -> ParsedDocument:
            return ParsedDocument(text=CONTRACTS_FIXTURE)

    service = DisclosureApplicationService(
        policy_repository=_policy_repo(),
        provider=FakeProvider(),
        default_context=_default_context(domain="contracts", policy_version="contracts-v1"),
        demo_vault_explorer_enabled=True,
        document_parser=_StubDocumentParser(),
    )
    request = service.build_document_request(
        filename="contract.pdf",
        file_bytes=b"%PDF-1.4 synthetic",
        task="Summarize the obligations of each party.",
        document_type=CONTRACT_DOCUMENT_TYPE,
        analysis_mode=None,
        strategy=DisclosureStrategy.REVERSIBLE_PSEUDONYMIZATION,
    )

    document_preview = service.preview_document(request)

    assert document_preview.preview.vault_explorer_token is not None


# --- export/execute/compare never populate it ----------------------------------


def test_execute_never_exposes_a_vault_explorer_token_field():
    service = _service(demo_vault_explorer_enabled=True)

    execution = service.execute(
        _app_request(HR_TEXT, strategy=DisclosureStrategy.REVERSIBLE_PSEUDONYMIZATION)
    )

    assert not hasattr(execution, "vault_explorer_token")


def test_compare_strategies_entries_never_expose_a_vault_explorer_token_field():
    service = _service(demo_vault_explorer_enabled=True)

    comparison = service.compare_strategies(_app_request(HR_TEXT))

    for entry in comparison.entries:
        assert not hasattr(entry, "vault_explorer_token")


def test_export_never_exposes_a_vault_explorer_token_field():
    from adaptive_disclosure_gateway.application.ingestion import ParsedDocument
    from adaptive_disclosure_gateway.application.presets import CONTRACT_DOCUMENT_TYPE
    from adaptive_disclosure_gateway.application.restore_handle import RestoreHandleSealer
    from tests.contracts_fixture import CONTRACTS_FIXTURE

    class _StubDocumentParser:
        parser_name = "stub_document_parser"
        parser_version = "test"

        def parse(self, *, safe_name: str, data: bytes) -> ParsedDocument:
            return ParsedDocument(text=CONTRACTS_FIXTURE)

    service = DisclosureApplicationService(
        policy_repository=_policy_repo(),
        provider=FakeProvider(),
        default_context=_default_context(domain="contracts", policy_version="contracts-v1"),
        demo_vault_explorer_enabled=True,
        restore_handle_sealer=RestoreHandleSealer(secret="a" * 32),
        document_parser=_StubDocumentParser(),
    )
    request = service.build_document_request(
        filename="contract.pdf",
        file_bytes=b"%PDF-1.4 synthetic",
        task="Summarize the obligations of each party.",
        document_type=CONTRACT_DOCUMENT_TYPE,
        analysis_mode=None,
        strategy=DisclosureStrategy.REVERSIBLE_PSEUDONYMIZATION,
    )

    export = service.export(request)

    assert not hasattr(export, "vault_explorer_token")


# --- adversarial: cross-preview isolation on a shared vault --------------------


def test_no_mapping_travels_between_two_previews_vault_explorer_tokens():
    """One shared service (one vault): preview B first (pseudonymizing
    Carlos Lima), then preview A (pseudonymizing Ana Souza) in the SAME
    session partition. A's vault-explorer response must contain neither
    Carlos's original nor his pseudonym, even though the shared vault holds
    both partitions' entries.
    """
    service = _service(demo_vault_explorer_enabled=True)

    preview_b = service.preview(
        _app_request(OTHER_TEXT, strategy=DisclosureStrategy.REVERSIBLE_PSEUDONYMIZATION)
    )
    view_b = service.explore_vault(preview_b.vault_explorer_token)
    carlos_pseudonym = next(e.pseudonym for e in view_b.entries if e.category == "employee_name")

    preview_a = service.preview(
        _app_request(HR_TEXT, strategy=DisclosureStrategy.REVERSIBLE_PSEUDONYMIZATION)
    )
    view_a = service.explore_vault(preview_a.vault_explorer_token)

    originals_a = [e.original for e in view_a.entries]
    pseudonyms_a = [e.pseudonym for e in view_a.entries]
    assert "Carlos Lima" not in originals_a
    assert carlos_pseudonym not in pseudonyms_a


def test_a_token_from_one_preview_cannot_be_reused_to_read_a_different_decisions_entries_via_forgery():
    """A tampered token (issued for one decision, then corrupted) must never
    resolve to ANY entries -- not a partial/degraded view of the original
    decision, and never another decision's data.
    """
    service = _service(demo_vault_explorer_enabled=True)
    preview = service.preview(
        _app_request(HR_TEXT, strategy=DisclosureStrategy.REVERSIBLE_PSEUDONYMIZATION)
    )
    token = preview.vault_explorer_token
    assert token is not None

    prefix, blob = token.split(".", 1)
    tampered = f"{prefix}.{blob[:-4]}zzzz"

    with pytest.raises(VaultExplorerReferenceError):
        service.explore_vault(tampered)
