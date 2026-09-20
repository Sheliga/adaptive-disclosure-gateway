"""T27 / issue #69: the HTTP surface of the demo transparency flag
(``ADG_ENABLE_DEMO_TRANSPARENCY`` / ``DisclosureApplicationService``'s
``demo_transparency_enabled``) and its inspection projection on
``POST /disclosure/preview`` / ``POST /documents/preview``.

Adversarial sections mirror ``tests/test_telemetry_privacy.py`` (span
attributes) and ``tests/test_api_no_leak.py`` (raw HTTP response text)
rather than inventing a new harness, per CLAUDE.md's no-leak invariant: a
change touching sensitive data needs an adversarial test asking whether a
sensitive value can escape through an alternative path, not just whether
the immediate field under test looks clean.
"""

from __future__ import annotations

from adaptive_disclosure_gateway.application.presets import CONTRACT_DOCUMENT_TYPE
from adaptive_disclosure_gateway.application.service import DisclosureApplicationService
from tests import telemetry_assertions
from tests.api_support import (
    HR_TEXT,
    RecordingProvider,
    build_client,
    build_service,
    default_context,
    policy_repository,
)
from tests.test_application_document_presets import StubContractParser

_assert_span_attributes_never_leak = telemetry_assertions.assert_span_attributes_never_leak

CONTRACT_TASK = "Summarize the obligations of each party and the deadlines."


def _document_client(service):
    return build_client(service)


def _upload_document_preview(client, *, document_parser_calls=None):
    return client.post(
        "/documents/preview",
        files={"file": ("contract.pdf", b"%PDF-1.4 synthetic", "application/pdf")},
        data={"task": CONTRACT_TASK, "document_type": CONTRACT_DOCUMENT_TYPE},
    )


# --- default (flag off) vs. enabled ------------------------------------------


def test_preview_inspection_is_null_when_demo_transparency_is_disabled():
    client = build_client(build_service(RecordingProvider(), demo_transparency_enabled=False))

    response = client.post(
        "/disclosure/preview", json={"text": HR_TEXT, "task": "summarize personnel record"}
    )

    assert response.status_code == 200
    body = response.json()
    assert "inspection" in body
    assert body["inspection"] is None


def test_preview_inspection_is_populated_when_demo_transparency_is_enabled():
    client = build_client(build_service(RecordingProvider(), demo_transparency_enabled=True))

    response = client.post(
        "/disclosure/preview", json={"text": HR_TEXT, "task": "summarize personnel record"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["inspection"] is not None
    assert body["inspection"]["available"] is True
    assert set(body["inspection"]) == {"available", "unavailable_reason", "segments"}
    for segment in body["inspection"]["segments"]:
        assert set(segment) == {"action", "category", "original", "disclosed"}


def test_documents_preview_inspection_is_null_when_disabled_and_populated_when_enabled():
    disabled_service = DisclosureApplicationService(
        policy_repository=policy_repository(),
        provider=RecordingProvider(),
        default_context=default_context(),
        document_parser=StubContractParser(),
        demo_transparency_enabled=False,
    )
    enabled_service = DisclosureApplicationService(
        policy_repository=policy_repository(),
        provider=RecordingProvider(),
        default_context=default_context(),
        document_parser=StubContractParser(),
        demo_transparency_enabled=True,
    )

    disabled_body = _upload_document_preview(_document_client(disabled_service)).json()
    enabled_body = _upload_document_preview(_document_client(enabled_service)).json()

    assert disabled_body["inspection"] is None
    assert enabled_body["inspection"] is not None
    assert enabled_body["inspection"]["available"] is True
    # confirmation_token is still present -- the flag must not touch the
    # document-surface confirmation mechanism.
    assert "confirmation_token" in enabled_body


def test_health_and_ready_are_unaffected_by_the_demo_transparency_flag():
    # FakeProvider specifically (not RecordingProvider, an unrecognized
    # provider class that /ready already reports as not-ready for reasons
    # unrelated to this flag) -- isolates this pin to the flag's own effect.
    from adaptive_disclosure_gateway.providers import FakeProvider

    disabled_client = build_client(build_service(FakeProvider(), demo_transparency_enabled=False))
    enabled_client = build_client(build_service(FakeProvider(), demo_transparency_enabled=True))

    assert disabled_client.get("/health").json() == enabled_client.get("/health").json()
    disabled_ready = disabled_client.get("/ready")
    enabled_ready = enabled_client.get("/ready")
    assert disabled_ready.status_code == enabled_ready.status_code == 200
    assert disabled_ready.json() == enabled_ready.json()


# --- adversarial: no pseudonym/original mapping travels anywhere ------------


SENSITIVE_NAME = "Ana Souza"
OTHER_TEXT = "Employee: Carlos Lima\nCPF: 987.654.321-00\nDepartment: Finance\n"


def test_no_mapping_travels_between_two_previews_on_a_shared_service_instance():
    """One service instance (shared in-process vault), transparency on:
    preview a text containing a sensitive value (pseudonymized under B2),
    then preview a DIFFERENT text without that value. The second response's
    raw JSON must contain neither the first value nor its pseudonym --
    proving the inspection surface exposes only THIS request's own decision,
    never anything derived from the shared vault's other entries.
    """
    service = build_service(RecordingProvider(), demo_transparency_enabled=True)
    client = build_client(service)

    first = client.post(
        "/disclosure/preview",
        json={"text": HR_TEXT, "task": "summarize", "strategy": "b2"},
    )
    assert first.status_code == 200
    first_body = first.json()
    employee_segment = next(
        s for s in first_body["inspection"]["segments"] if s["category"] == "employee_name"
    )
    pseudonym = employee_segment["disclosed"]
    assert pseudonym
    assert SENSITIVE_NAME not in pseudonym

    second = client.post(
        "/disclosure/preview",
        json={"text": OTHER_TEXT, "task": "summarize", "strategy": "b2"},
    )
    assert second.status_code == 200
    raw = second.text
    assert SENSITIVE_NAME not in raw
    assert pseudonym not in raw
    # The declared field set of the populated inspection model never grows a
    # mapping-shaped field (e.g. no "mapping"/"vault"/"pseudonyms" key).
    second_body = second.json()
    assert set(second_body["inspection"]) == {"available", "unavailable_reason", "segments"}
    for segment in second_body["inspection"]["segments"]:
        assert set(segment) == {"action", "category", "original", "disclosed"}


# --- adversarial: side channels (span attributes, raw response) ------------


def test_demo_transparency_span_attributes_never_leak_sensitive_values(recorded_spans):
    service = build_service(RecordingProvider(), demo_transparency_enabled=True)
    client = build_client(service)

    response = client.post(
        "/disclosure/preview",
        json={"text": HR_TEXT, "task": "summarize", "strategy": "b2"},
    )
    assert response.status_code == 200
    body = response.json()
    employee_segment = next(
        s for s in body["inspection"]["segments"] if s["category"] == "employee_name"
    )
    pseudonym = employee_segment["disclosed"]

    finished = recorded_spans.get_finished_spans()
    _assert_span_attributes_never_leak(
        finished, SENSITIVE_NAME, "123.456.789-09", "8500.00", HR_TEXT, pseudonym
    )


def test_demo_transparency_inspection_shows_the_authorized_value_for_this_request_only():
    """The inspection surface is DELIBERATELY authorized to show the
    original value next to what was disclosed for THIS request's own
    decision (that is the entire pedagogical point of T27 / issue #69 --
    "reutilizar decision.result.transformations como fonte de verdade").
    What must never happen is the SAME value/pseudonym pair leaking into a
    DIFFERENT request's response -- covered by the cross-request test above.
    This test pins the (expected, authorized) positive case so a future
    change does not confuse "shows the original for this request" with a
    leak and silently strip it.
    """
    service = build_service(RecordingProvider(), demo_transparency_enabled=True)
    client = build_client(service)

    response = client.post(
        "/disclosure/preview",
        json={"text": HR_TEXT, "task": "summarize", "strategy": "b2"},
    )

    body = response.json()
    employee_segment = next(
        s for s in body["inspection"]["segments"] if s["category"] == "employee_name"
    )
    assert employee_segment["original"] == SENSITIVE_NAME
    assert employee_segment["disclosed"] != SENSITIVE_NAME
    assert employee_segment["disclosed"].startswith("PSEUDO-")
    # The plain external_payload (the historical field) still never carries
    # the original -- inspection.segments[*].original is the one place this
    # request's own authorized value is deliberately shown.
    assert SENSITIVE_NAME not in body["external_payload"]
