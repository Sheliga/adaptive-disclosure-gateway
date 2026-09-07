"""Regression coverage for the leak-check hardening described in
``tests/telemetry_assertions.py``'s module docstring.

The previous version of ``_assert_span_attributes_never_leak`` (formerly
private to ``tests/test_telemetry_privacy.py``) substring-matched every span
attribute's ``str()`` form, including numeric ones. That is a false-positive
generator, not a real leak detector, for any numeric attribute: an int or
float attribute's digits can coincidentally match an unrelated forbidden
value's digits (this already happened once with ``duration_ms`` noise -- see
docs/implementation-status.md's fixed-flake entry). These tests pin the
property that must hold from now on: a numeric or boolean attribute's digits
can never trip the check, while a real leak through a string (or
string-sequence) attribute is still caught every time.
"""

from __future__ import annotations

import pytest

from tests.telemetry_assertions import assert_span_attributes_never_leak


class _FakeSpan:
    def __init__(self, attributes: dict) -> None:
        self.attributes = attributes


def test_int_attribute_containing_forbidden_digits_is_not_flagged_as_a_leak():
    # A provider's transmitted-byte count of 8500 must not trip the check
    # just because "8500" also happens to be a fixture salary amount --
    # this is exactly the class of false positive Part 2 (the providers
    # package exposing transmitted_bytes) makes more likely to occur.
    span = _FakeSpan({"providers.transmitted_bytes": 8500})
    assert_span_attributes_never_leak([span], "8500")


def test_float_attribute_containing_forbidden_digits_is_not_flagged_as_a_leak():
    # The original incident: unrounded time.perf_counter() noise containing
    # the same digit run as an unrelated forbidden value.
    span = _FakeSpan({"static_sanitization.duration_ms": 0.0850000069476664})
    assert_span_attributes_never_leak([span], "8500")


def test_bool_attribute_is_not_flagged_as_a_leak():
    span = _FakeSpan({"static_sanitization.blocked": True})
    assert_span_attributes_never_leak([span], "True")


def test_string_attribute_containing_forbidden_value_is_still_flagged_as_a_leak():
    span = _FakeSpan({"debug.note": "salary was R$ 8500.00 this month"})
    with pytest.raises(AssertionError):
        assert_span_attributes_never_leak([span], "8500")


def test_string_sequence_attribute_containing_forbidden_value_is_still_flagged_as_a_leak():
    span = _FakeSpan({"static_sanitization.categories": ("department", "Ana Souza")})
    with pytest.raises(AssertionError):
        assert_span_attributes_never_leak([span], "Ana Souza")
