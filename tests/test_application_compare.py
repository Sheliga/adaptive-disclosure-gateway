"""T20 / issue #28's "Compare strategies" slice (issue #29/#41):
``DisclosureApplicationService.compare_strategies``.

This is a PREVIEW-based comparison and must never call a provider for any
of the five strategies -- see ``application/service.py``'s and
``application/contracts.py``'s module docstrings for why. It is also not an
evaluation surface: it never touches the oracle or ``experiments.scoring``
and never ranks/scores a "best" strategy -- see
``tests/test_application_ground_truth_isolation.py``, which already covers
the whole ``application`` package by AST inspection, including the new
``compare_strategies``/``StrategyComparison`` additions.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from pathlib import Path

from adaptive_disclosure_gateway.application.contracts import (
    CANONICAL_COMPARISON_ORDER,
    DisclosureApplicationRequest,
    DisclosureStrategy,
    GovernanceOverrides,
)
from adaptive_disclosure_gateway.application.ingestion import normalize_text
from adaptive_disclosure_gateway.application.service import DisclosureApplicationService
from adaptive_disclosure_gateway.domain import GovernanceContext, Treatment
from adaptive_disclosure_gateway.policies import PolicyRepository
from adaptive_disclosure_gateway.providers import (
    ProviderRequest,
    ProviderResponse,
    count_transmitted_bytes,
)

POLICY_DIR = Path(__file__).parents[1] / "configs" / "policies"

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
class NeverCallMeProvider:
    """A provider whose ``generate`` must never be invoked -- used to prove
    ``compare_strategies`` never reaches the provider boundary, for any of
    the five strategies.
    """

    provider_class: str = "fake"

    def generate(self, request: ProviderRequest) -> ProviderResponse:  # pragma: no cover
        raise AssertionError("compare_strategies must never call the provider")


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


def _service(provider, **context_overrides) -> DisclosureApplicationService:
    return DisclosureApplicationService(
        policy_repository=_policy_repo(),
        provider=provider,
        default_context=_default_context(**context_overrides),
    )


def _app_request(text: str, task: str = "summarize personnel record", **gov):
    return DisclosureApplicationRequest(
        content=normalize_text(text),
        task=task,
        strategy=DisclosureStrategy.RECOMMENDED,
        governance=GovernanceOverrides(**gov),
    )


# --- 1. compare_strategies never calls the provider --------------------------


def test_compare_strategies_never_calls_the_provider():
    service = _service(NeverCallMeProvider())

    comparison = service.compare_strategies(_app_request(HR_TEXT))

    assert len(comparison.entries) == 5


# --- 2. canonical order B0 -> B1 -> B2 -> B3 -> B4, all five present once ----


def test_compare_strategies_returns_entries_in_canonical_order():
    service = _service(RecordingProvider())

    comparison = service.compare_strategies(_app_request(HR_TEXT))

    assert tuple(entry.strategy for entry in comparison.entries) == CANONICAL_COMPARISON_ORDER
    assert CANONICAL_COMPARISON_ORDER == (
        DisclosureStrategy.DIRECT,
        DisclosureStrategy.STATIC_SANITIZATION,
        DisclosureStrategy.REVERSIBLE_PSEUDONYMIZATION,
        DisclosureStrategy.TASK_AWARE,
        DisclosureStrategy.POLICY_GOVERNED,
    )


def test_compare_strategies_never_repeats_or_omits_a_strategy():
    service = _service(RecordingProvider())

    comparison = service.compare_strategies(_app_request(HR_TEXT))

    strategies = [entry.strategy for entry in comparison.entries]
    assert len(strategies) == 5
    assert set(strategies) == {
        DisclosureStrategy.DIRECT,
        DisclosureStrategy.STATIC_SANITIZATION,
        DisclosureStrategy.REVERSIBLE_PSEUDONYMIZATION,
        DisclosureStrategy.TASK_AWARE,
        DisclosureStrategy.POLICY_GOVERNED,
    }


# --- 3. each entry equals what preview() itself returns for that strategy ---


def test_each_entry_matches_a_direct_preview_call_for_the_same_strategy():
    service = _service(RecordingProvider())
    request = _app_request(HR_TEXT)

    comparison = service.compare_strategies(request)

    for entry in comparison.entries:
        direct_preview = service.preview(dataclasses.replace(request, strategy=entry.strategy))
        assert entry.summary == direct_preview.summary
        assert entry.external_payload == direct_preview.external_payload
        assert entry.payload_byte_count == direct_preview.payload_byte_count
        assert entry.treatment == direct_preview.treatment


# --- 4. every entry ran against byte-identical content/task/governance ------


def test_every_entry_shares_identical_governance_and_provider_mode():
    service = _service(RecordingProvider())

    comparison = service.compare_strategies(_app_request(HR_TEXT))

    assert comparison.governance.domain == "hr"
    assert comparison.governance.purpose == "team_summary"
    assert comparison.provider_mode.provider_class == "fake"


# --- 5. recommended is True for exactly one entry ----------------------------


def test_recommended_is_true_for_exactly_one_entry_matching_policy_governed():
    service = _service(RecordingProvider())

    comparison = service.compare_strategies(_app_request(HR_TEXT))

    recommended_entries = [entry for entry in comparison.entries if entry.recommended]
    assert len(recommended_entries) == 1
    assert recommended_entries[0].treatment is Treatment.POLICY_GOVERNED
    assert recommended_entries[0].strategy is DisclosureStrategy.POLICY_GOVERNED


def test_recommended_strategy_is_never_the_recommended_sentinel_value():
    """Every entry's ``strategy`` is an explicit b0-b4 value -- never the
    ``RECOMMENDED`` sentinel, even for the entry that happens to be the
    recommended one.
    """
    service = _service(RecordingProvider())

    comparison = service.compare_strategies(_app_request(HR_TEXT))

    assert all(entry.strategy != DisclosureStrategy.RECOMMENDED for entry in comparison.entries)


# --- 6. unsafe_control_baseline is True only for B0, from the capability marker


def test_unsafe_control_baseline_is_true_only_for_b0():
    service = _service(RecordingProvider())

    comparison = service.compare_strategies(_app_request(HR_TEXT))

    baseline_entries = [entry for entry in comparison.entries if entry.unsafe_control_baseline]
    assert len(baseline_entries) == 1
    assert baseline_entries[0].strategy is DisclosureStrategy.DIRECT
    assert baseline_entries[0].treatment is Treatment.DIRECT


# --- 7. B2/B3/B4 entries sharing the same original produce the same pseudonym


def _employee_line_value(payload: str) -> str:
    for line in payload.splitlines():
        if line.startswith("Employee:"):
            return line.split("Employee:", 1)[1].strip()
    raise AssertionError("no 'Employee:' line found in payload")


def test_b2_b3_b4_entries_share_one_pseudonym_for_the_same_original():
    service = _service(RecordingProvider())
    # B3 -- Task-aware only pseudonymizes employee_name when the task makes
    # it relevant (see task_analysis/deterministic.py's indicator table);
    # "identify the employee by name" is one of its recognized indicators,
    # so all three treatments pseudonymize (rather than B3 removing it as
    # not-task-relevant), making this a meaningful shared-vault check.
    request = _app_request(
        HR_TEXT, task="Identify the employee by name and summarize the personnel record."
    )

    comparison = service.compare_strategies(request)
    by_strategy = {entry.strategy: entry for entry in comparison.entries}

    b2_token = _employee_line_value(
        by_strategy[DisclosureStrategy.REVERSIBLE_PSEUDONYMIZATION].external_payload
    )
    b3_token = _employee_line_value(by_strategy[DisclosureStrategy.TASK_AWARE].external_payload)
    b4_token = _employee_line_value(
        by_strategy[DisclosureStrategy.POLICY_GOVERNED].external_payload
    )

    # All three pseudonymize the name category under this policy -- the
    # token B2 produced for "Ana Souza" must be the identical token B3/B4
    # produce too, because all three entries share this service's one vault.
    assert b2_token != "Ana Souza"
    assert b2_token == b3_token == b4_token


# --- 11. a blocked strategy still produces a well-formed entry --------------


def test_blocked_content_still_produces_a_well_formed_entry_with_no_provider_call():
    """Under hr-v1, ``medical_data`` is ``block_request`` for every treatment
    that actually consults policy (B1-B4). B0 -- Direct never blocks at all
    (it is the unsafe control baseline, see ``transformations/direct_disclosure.py``)
    -- so its own entry stays ``allowed``, which is itself well-formed and
    correct, not a defect in this comparison. ``NeverCallMeProvider`` proves
    no strategy -- blocked or not -- ever reaches the provider.
    """
    service = _service(NeverCallMeProvider())

    comparison = service.compare_strategies(_app_request(HR_TEXT_WITH_MEDICAL))
    by_strategy = {entry.strategy: entry for entry in comparison.entries}

    assert len(comparison.entries) == 5
    assert by_strategy[DisclosureStrategy.DIRECT].summary.status == "allowed"
    for strategy in (
        DisclosureStrategy.STATIC_SANITIZATION,
        DisclosureStrategy.REVERSIBLE_PSEUDONYMIZATION,
        DisclosureStrategy.TASK_AWARE,
        DisclosureStrategy.POLICY_GOVERNED,
    ):
        entry = by_strategy[strategy]
        assert entry.summary.status == "blocked", strategy
        assert entry.external_payload == ""
