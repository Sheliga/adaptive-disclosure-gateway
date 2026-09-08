"""Pins the OTel acceptance criterion: spans may carry categories, counts and
timing only -- never the detected value, the raw text, the payload, or (for
B2) the pseudonym mapping / vault content.
"""

from pathlib import Path

from adaptive_disclosure_gateway.detection import Detector
from adaptive_disclosure_gateway.domain import DisclosureRequest, GovernanceContext
from adaptive_disclosure_gateway.policies import PolicyRepository
from adaptive_disclosure_gateway.transformations import (
    PolicyGovernedDiscloser,
    ReversiblePseudonymizer,
    StaticSanitizer,
    TaskAwareDiscloser,
)
from adaptive_disclosure_gateway.transformations.direct_disclosure import DirectDiscloser
from adaptive_disclosure_gateway.vault import InMemoryVault
from tests import telemetry_assertions

POLICY_DIR = Path(__file__).parents[1] / "configs" / "policies"

SECRET_TEXT = (
    "Employee: Ana Souza\nCPF: 123.456.789-09\nSalary: R$ 8500.00\nDepartment: Engineering\n"
)

# Issue #16 (2b): a configured-but-unparseable GENERALIZE value, used below to
# confirm the fail-closed pre-pass doesn't leak the unparseable value through
# telemetry either -- not just through the external payload.
UNPARSEABLE_SALARY_TEXT = "Salary: to be negotiated later\n"

# The substring-leak scan itself now lives in tests/telemetry_assertions.py
# (hardened to skip numeric/boolean attributes -- see that module's
# docstring): aliased here under the previous private name so every call
# site below is unchanged.
_assert_span_attributes_never_leak = telemetry_assertions.assert_span_attributes_never_leak


def test_b0_span_attributes_never_contain_the_raw_text_even_though_it_is_the_payload(
    recorded_spans,
):
    # B0's external payload *is* the raw input text (issue #25) -- the one
    # treatment where the usual "don't log the payload" span rule and "don't
    # log the raw text" span rule are the same rule, checked against the
    # same string. A naive implementation logging e.g. the payload "for
    # debugging" would be an actual leak here, not a false positive.
    request = DisclosureRequest(
        text=SECRET_TEXT,
        task="summarize",
        context=GovernanceContext(domain="hr", purpose="team_summary", policy_version="hr-v1"),
    )

    result = DirectDiscloser().sanitize(request, spans=[])

    finished = recorded_spans.get_finished_spans()
    _assert_span_attributes_never_leak(finished, "Ana Souza", "123.456.789-09", "8500", SECRET_TEXT)
    assert result.external_payload == SECRET_TEXT


def test_detector_span_attributes_never_contain_detected_values_or_raw_text(recorded_spans):
    Detector().detect(SECRET_TEXT)

    finished = recorded_spans.get_finished_spans()
    _assert_span_attributes_never_leak(finished, "Ana Souza", "123.456.789-09", "8500", SECRET_TEXT)


def test_b1_span_attributes_never_contain_detected_values_or_payload(recorded_spans):
    request = DisclosureRequest(
        text=SECRET_TEXT,
        task="summarize",
        context=GovernanceContext(domain="hr", purpose="team_summary", policy_version="hr-v1"),
    )
    spans = Detector().detect(SECRET_TEXT)
    recorded_spans.clear()  # isolate Static Sanitization (B1)'s own span from the detector's

    result = StaticSanitizer().sanitize(request, spans)

    finished = recorded_spans.get_finished_spans()
    _assert_span_attributes_never_leak(
        finished, "Ana Souza", "123.456.789-09", "8500", SECRET_TEXT, result.external_payload
    )


def test_b2_span_attributes_never_contain_detected_values_payload_or_pseudonym_mapping(
    recorded_spans,
):
    request = DisclosureRequest(
        text=SECRET_TEXT,
        task="summarize",
        context=GovernanceContext(
            domain="hr",
            purpose="team_summary",
            requester_id="u1",
            policy_version="hr-v1",
            session_id="s1",
        ),
    )
    spans = Detector().detect(SECRET_TEXT)
    recorded_spans.clear()  # isolate B2's own spans from the detector's

    pseudonymizer = ReversiblePseudonymizer(
        vault=InMemoryVault(), policy_repository=PolicyRepository.from_directory(POLICY_DIR)
    )
    result = pseudonymizer.sanitize(request, spans)

    pseudonym = next(t.transformed for t in result.transformations if t.category == "employee_name")
    # The mapping itself (which original a pseudonym stands for) is exactly
    # what the vault protects; a telemetry attribute combining the two would
    # leak the mapping even though neither string alone is sensitive here.
    pseudonym_mapping = f"Ana Souza:{pseudonym}"

    finished = recorded_spans.get_finished_spans()
    _assert_span_attributes_never_leak(
        finished,
        "Ana Souza",
        "123.456.789-09",
        "8500",
        SECRET_TEXT,
        result.external_payload,
        pseudonym_mapping,
    )


def test_b1_configured_unparseable_generalize_span_attributes_do_not_leak_the_value(
    recorded_spans,
):
    request = DisclosureRequest(
        text=UNPARSEABLE_SALARY_TEXT,
        task="summarize",
        context=GovernanceContext(domain="hr", purpose="team_summary", policy_version="hr-v1"),
    )
    spans = Detector().detect(UNPARSEABLE_SALARY_TEXT)
    recorded_spans.clear()  # isolate Static Sanitization (B1)'s own span from the detector's

    result = StaticSanitizer().sanitize(request, spans)

    assert result.status == "blocked"
    finished = recorded_spans.get_finished_spans()
    _assert_span_attributes_never_leak(finished, "to be negotiated later", UNPARSEABLE_SALARY_TEXT)


def test_b2_configured_unparseable_generalize_span_attributes_do_not_leak_the_value(
    recorded_spans,
):
    request = DisclosureRequest(
        text=UNPARSEABLE_SALARY_TEXT,
        task="summarize",
        context=GovernanceContext(
            domain="hr", purpose="team_summary", requester_id="u1", policy_version="hr-v1"
        ),
    )
    spans = Detector().detect(UNPARSEABLE_SALARY_TEXT)
    recorded_spans.clear()  # isolate B2's own spans from the detector's

    pseudonymizer = ReversiblePseudonymizer(
        vault=InMemoryVault(), policy_repository=PolicyRepository.from_directory(POLICY_DIR)
    )
    result = pseudonymizer.sanitize(request, spans)

    assert result.status == "blocked"
    finished = recorded_spans.get_finished_spans()
    _assert_span_attributes_never_leak(finished, "to be negotiated later", UNPARSEABLE_SALARY_TEXT)


def test_b3_span_attributes_never_contain_detected_values_payload_or_pseudonym_mapping(
    recorded_spans,
):
    request = DisclosureRequest(
        text=SECRET_TEXT,
        task=(
            "Determine whether this employee's salary falls within the standard "
            "compensation band for their department. You do not need the employee's "
            "name or CPF to answer."
        ),
        context=GovernanceContext(
            domain="hr",
            purpose="salary_analysis",
            requester_id="u1",
            policy_version="hr-v1",
            session_id="s1",
        ),
    )
    spans = Detector().detect(SECRET_TEXT)
    recorded_spans.clear()  # isolate B3's own spans from the detector's

    discloser = TaskAwareDiscloser(
        vault=InMemoryVault(), policy_repository=PolicyRepository.from_directory(POLICY_DIR)
    )
    result = discloser.sanitize(request, spans)

    pseudonym = next(t.transformed for t in result.transformations if t.category == "employee_name")
    pseudonym_mapping = f"Ana Souza:{pseudonym}"

    finished = recorded_spans.get_finished_spans()
    _assert_span_attributes_never_leak(
        finished,
        "Ana Souza",
        "123.456.789-09",
        "8500",
        SECRET_TEXT,
        result.external_payload,
        pseudonym_mapping,
        request.task,
    )


def test_b3_reconstruct_span_attributes_never_contain_original_values(recorded_spans):
    request = DisclosureRequest(
        text="Employee: Ana Souza\n",
        task="Draft the opening line of an internal announcement addressed by name to this employee.",
        context=GovernanceContext(
            domain="hr",
            purpose="team_summary",
            requester_id="u1",
            policy_version="hr-v1",
            session_id="s1",
        ),
    )
    spans = Detector().detect(request.text)
    discloser = TaskAwareDiscloser(
        vault=InMemoryVault(), policy_repository=PolicyRepository.from_directory(POLICY_DIR)
    )
    result = discloser.sanitize(request, spans)
    pseudonym = next(t.transformed for t in result.transformations if t.category == "employee_name")
    recorded_spans.clear()  # isolate reconstruct()'s own span

    response_text = f"Hello {pseudonym}, welcome to the team."
    reconstructed = discloser.reconstruct(response_text, result, request.context)

    finished = recorded_spans.get_finished_spans()
    _assert_span_attributes_never_leak(finished, "Ana Souza", request.text, reconstructed)


def test_b4_span_attributes_never_contain_detected_values_payload_or_pseudonym_mapping(
    recorded_spans,
):
    request = DisclosureRequest(
        text=SECRET_TEXT,
        task=(
            "Determine whether this employee's salary falls within the standard "
            "compensation band for their department. You do not need the employee's "
            "name or CPF to answer."
        ),
        context=GovernanceContext(
            domain="hr",
            purpose="salary_analysis",
            requester_role="hr_analyst",
            requester_id="u1",
            policy_version="hr-v2",
            session_id="s1",
        ),
    )
    spans = Detector().detect(SECRET_TEXT)
    recorded_spans.clear()  # isolate B4's own spans from the detector's

    discloser = PolicyGovernedDiscloser(
        vault=InMemoryVault(), policy_repository=PolicyRepository.from_directory(POLICY_DIR)
    )
    result = discloser.sanitize(request, spans)

    pseudonym = next(t.transformed for t in result.transformations if t.category == "employee_name")
    pseudonym_mapping = f"Ana Souza:{pseudonym}"

    finished = recorded_spans.get_finished_spans()
    _assert_span_attributes_never_leak(
        finished,
        "Ana Souza",
        "123.456.789-09",
        "8500",
        SECRET_TEXT,
        result.external_payload,
        pseudonym_mapping,
        request.task,
    )


def test_b4_span_attributes_never_leak_when_policy_blocks_a_category(recorded_spans):
    # A hard-blocked policy path (medical_data) is exactly the case where a
    # naive implementation might be tempted to log "why" using the detected
    # value -- confirms it still doesn't.
    text = SECRET_TEXT + "Medical notes: Reports chronic migraine and requested leave.\n"
    request = DisclosureRequest(
        text=text,
        task="Summarize this employee's medical leave.",
        context=GovernanceContext(
            domain="hr",
            purpose="team_summary",
            policy_version="hr-v2",
            session_id="s1",
        ),
    )
    spans = Detector().detect(text)
    recorded_spans.clear()

    discloser = PolicyGovernedDiscloser(
        vault=InMemoryVault(), policy_repository=PolicyRepository.from_directory(POLICY_DIR)
    )
    result = discloser.sanitize(request, spans)

    assert result.status == "blocked"
    finished = recorded_spans.get_finished_spans()
    _assert_span_attributes_never_leak(
        finished,
        "Ana Souza",
        "123.456.789-09",
        "8500",
        "chronic migraine",
        text,
        request.task,
    )


def test_b4_reconstruct_span_attributes_never_contain_original_values(recorded_spans):
    request = DisclosureRequest(
        text="Employee: Ana Souza\n",
        task="Draft the opening line of an internal announcement addressed by name to this employee.",
        context=GovernanceContext(
            domain="hr",
            purpose="team_summary",
            provider_class="internal_llm",
            requester_id="u1",
            policy_version="hr-v2",
            session_id="s1",
        ),
    )
    spans = Detector().detect(request.text)
    discloser = PolicyGovernedDiscloser(
        vault=InMemoryVault(), policy_repository=PolicyRepository.from_directory(POLICY_DIR)
    )
    result = discloser.sanitize(request, spans)
    pseudonym = next(t.transformed for t in result.transformations if t.category == "employee_name")
    recorded_spans.clear()  # isolate reconstruct()'s own span

    response_text = f"Hello {pseudonym}, welcome to the team."
    reconstructed = discloser.reconstruct(response_text, result, request.context)

    finished = recorded_spans.get_finished_spans()
    _assert_span_attributes_never_leak(finished, "Ana Souza", request.text, reconstructed)


def test_b2_reconstruct_span_attributes_never_contain_original_values(recorded_spans):
    request = DisclosureRequest(
        text=SECRET_TEXT,
        task="summarize",
        context=GovernanceContext(
            domain="hr",
            purpose="team_summary",
            requester_id="u1",
            policy_version="hr-v1",
            session_id="s1",
        ),
    )
    spans = Detector().detect(SECRET_TEXT)
    pseudonymizer = ReversiblePseudonymizer(
        vault=InMemoryVault(), policy_repository=PolicyRepository.from_directory(POLICY_DIR)
    )
    result = pseudonymizer.sanitize(request, spans)
    pseudonym = next(t.transformed for t in result.transformations if t.category == "employee_name")
    recorded_spans.clear()  # isolate reconstruct()'s own span

    response_text = f"Contact {pseudonym} about the leave request."
    reconstructed = pseudonymizer.reconstruct(response_text, result, request.context)

    finished = recorded_spans.get_finished_spans()
    _assert_span_attributes_never_leak(finished, "Ana Souza", SECRET_TEXT, reconstructed)
