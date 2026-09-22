from adaptive_disclosure_gateway.detection import Detector
from adaptive_disclosure_gateway.domain import (
    DisclosureAction,
    DisclosureRequest,
    GovernanceContext,
    SensitiveSpan,
)
from adaptive_disclosure_gateway.transformations import StaticSanitizer


def _request(text: str, **context_overrides) -> DisclosureRequest:
    values = {
        "domain": "hr",
        "purpose": "team_summary",
        "policy_version": "hr-v1",
    }
    values.update(context_overrides)
    return DisclosureRequest(text=text, task="summarize", context=GovernanceContext(**values))


def test_remove_action_drops_value_and_does_not_leak_original():
    text = "CPF: 123.456.789-09 recorded."
    request = _request(text)
    spans = Detector().detect(text)

    result = StaticSanitizer().sanitize(request, spans)

    assert "123.456.789-09" not in result.external_payload
    transformation = next(t for t in result.transformations if t.category == "cpf")
    assert transformation.transformed is None
    assert transformation.action is DisclosureAction.REMOVE


def test_generalize_action_replaces_salary_without_leaking_original_value():
    text = "Salary: R$ 8500.00\n"
    request = _request(text)
    spans = Detector().detect(text)

    result = StaticSanitizer().sanitize(request, spans)

    assert "8500.00" not in result.external_payload
    transformation = next(t for t in result.transformations if t.category == "salary")
    assert transformation.action is DisclosureAction.GENERALIZE
    # Issue #16: GENERALIZE must be a real band, not a fixed placeholder --
    # this is what makes it distinguishable from REMOVE's `transformed=None`.
    assert transformation.transformed == "R$ 5000-10000"


def test_generalize_action_blocks_when_salary_value_has_trailing_prose():
    # Issue #93 / M3 (post-pilot-v5): the detector's labeled-line rule
    # captures the whole rest of the line as the span value, so a line with
    # trailing prose after the amount (a real shape the pre-#93 permissive
    # float regex used to silently misparse) is no longer a value the closed
    # amount grammar accepts at all -- it must fail closed, not partially
    # disclose a wrong band.
    text = "Salary: R$ 8500.00 was paid.\n"
    request = _request(text)
    spans = Detector().detect(text)
    assert any(s.category == "salary" for s in spans)  # detected, just unparseable as an amount

    result = StaticSanitizer().sanitize(request, spans)

    assert result.status == "blocked"
    assert result.external_payload == ""
    assert "8500.00" not in result.external_payload


def test_unconfigured_generalize_category_fails_closed_instead_of_disclosing(monkeypatch):
    # If a future edit routes a new category through GENERALIZE without also
    # registering a strategy for it in generalization.py, the request must
    # block, not silently emit the original value (issue #16).
    import adaptive_disclosure_gateway.transformations.static_sanitization as static_sanitization_module

    monkeypatch.setitem(static_sanitization_module.ACTIONS, "bonus", DisclosureAction.GENERALIZE)
    text = "Bonus: R$ 500.00 was paid.\n"
    request = _request(text)
    spans = [SensitiveSpan(category="bonus", value="R$ 500.00", start=7, end=16)]

    result = StaticSanitizer().sanitize(request, spans)

    assert result.status == "blocked"
    assert "500.00" not in result.external_payload


def test_configured_generalize_category_with_unparseable_value_fails_closed_not_raises():
    # Issue #16 (2b): "salary" *is* configured for GENERALIZE, but a free-text
    # value the strategy cannot parse must block the request -- not let
    # GeneralizationError escape mid-slice with a half-built payload.
    text = "Salary: to be negotiated later\n"
    request = _request(text)
    spans = Detector().detect(text)
    assert any(s.category == "salary" for s in spans)  # detected, just unparseable

    result = StaticSanitizer().sanitize(request, spans)

    assert result.status == "blocked"
    assert result.external_payload == ""
    assert "to be negotiated later" not in result.external_payload


def test_preserve_action_keeps_department_value_in_payload():
    text = "Department: Engineering\n"
    request = _request(text)
    spans = Detector().detect(text)

    result = StaticSanitizer().sanitize(request, spans)

    assert "Engineering" in result.external_payload
    transformation = next(t for t in result.transformations if t.category == "department")
    assert transformation.action is DisclosureAction.PRESERVE
    assert transformation.transformed == "Engineering"


def test_medical_data_blocks_entire_request_and_suppresses_other_spans():
    text = "Employee: Ana Souza\nMedical notes: Reports chronic migraine.\n"
    request = _request(text)
    spans = Detector().detect(text)

    result = StaticSanitizer().sanitize(request, spans)

    assert result.status == "blocked"
    assert result.external_payload == ""
    assert result.transformations == []
    assert "Ana Souza" not in result.external_payload


def test_unmapped_category_fails_closed_instead_of_leaking():
    request = _request("some free text value here")
    spans = [SensitiveSpan(category="unknown_category", value="value here", start=15, end=25)]

    result = StaticSanitizer().sanitize(request, spans)

    assert result.status == "blocked"
    assert "value here" not in result.external_payload


def test_sanitizer_output_is_independent_of_governance_context():
    text = "Department: Engineering\n"
    spans = Detector().detect(text)

    result_a = StaticSanitizer().sanitize(
        _request(text, purpose="team_summary", requester_role="hr_viewer"), spans
    )
    result_b = StaticSanitizer().sanitize(
        _request(text, purpose="salary_analysis", requester_role="hr_admin"), spans
    )

    assert result_a.external_payload == result_b.external_payload
    assert result_a.transformations == result_b.transformations
    assert result_a.status == result_b.status


def test_sanitizer_is_deterministic_across_runs():
    text = "Salary: R$ 8500.00\nDepartment: Engineering\n"
    request = _request(text)
    spans = Detector().detect(text)

    first = StaticSanitizer().sanitize(request, spans)
    second = StaticSanitizer().sanitize(request, spans)

    assert first == second


# Issue #17: a span with missing/malformed offsets used to reach
# `_allowed_result`'s `span.start or 0, span.end or 0` coercion, which turned
# `start=None, end=None` into a zero-length slice at offset 0. The cursor
# never advanced, so the trailing `text[cursor:]` re-appended the entire
# original text -- an "allowed" result claiming a REMOVE had happened while
# actually disclosing the full sensitive value. SensitiveSpan now requires
# valid offsets, so such a span can no longer be constructed through the
# normal constructor; `model_construct` bypasses that validation entirely
# (it skips Pydantic's validators), so it is the only way left to get a
# malformed span into the sanitizer, and is used below to prove the boundary
# check in `StaticSanitizer.sanitize` -- not just the model -- stops it.


def test_span_with_missing_offsets_bypassing_model_is_blocked_not_leaked():
    text = "CPF: 123.456.789-09 recorded."
    request = _request(text)
    malformed = SensitiveSpan.model_construct(
        category="cpf", value="123.456.789-09", start=None, end=None, confidence=None
    )

    result = StaticSanitizer().sanitize(request, [malformed])

    assert result.status == "blocked"
    assert result.external_payload == ""
    assert "123.456.789-09" not in result.external_payload


def test_span_with_negative_start_bypassing_model_is_blocked():
    text = "CPF: 123.456.789-09 recorded."
    request = _request(text)
    malformed = SensitiveSpan.model_construct(
        category="cpf", value="123.456.789-09", start=-5, end=20, confidence=None
    )

    result = StaticSanitizer().sanitize(request, [malformed])

    assert result.status == "blocked"
    assert "123.456.789-09" not in result.external_payload


def test_span_with_inverted_offsets_bypassing_model_is_blocked():
    text = "CPF: 123.456.789-09 recorded."
    request = _request(text)
    malformed = SensitiveSpan.model_construct(
        category="cpf", value="123.456.789-09", start=20, end=5, confidence=None
    )

    result = StaticSanitizer().sanitize(request, [malformed])

    assert result.status == "blocked"
    assert "123.456.789-09" not in result.external_payload


def test_span_with_zero_length_offsets_bypassing_model_is_blocked():
    text = "CPF: 123.456.789-09 recorded."
    request = _request(text)
    malformed = SensitiveSpan.model_construct(
        category="cpf", value="123.456.789-09", start=5, end=5, confidence=None
    )

    result = StaticSanitizer().sanitize(request, [malformed])

    assert result.status == "blocked"
    assert "123.456.789-09" not in result.external_payload


def test_span_with_out_of_bounds_end_is_blocked():
    text = "CPF: 123.456.789-09 recorded."
    request = _request(text)
    # A well-formed SensitiveSpan (passes the model's own validator) whose
    # `end` still runs past the actual source text -- only catchable at the
    # boundary, since the model never sees `text`.
    out_of_bounds = SensitiveSpan(category="cpf", value="123.456.789-09", start=5, end=1000)

    result = StaticSanitizer().sanitize(request, [out_of_bounds])

    assert result.status == "blocked"
    assert "123.456.789-09" not in result.external_payload


def test_span_with_value_offset_mismatch_is_blocked():
    text = "CPF: 123.456.789-09 recorded."
    request = _request(text)
    # Offsets are in-bounds and well-formed, but they point at a different
    # slice of `text` than the one the span claims as its value.
    mismatched = SensitiveSpan(category="cpf", value="123.456.789-09", start=0, end=4)

    result = StaticSanitizer().sanitize(request, [mismatched])

    assert result.status == "blocked"
    assert "123.456.789-09" not in result.external_payload
