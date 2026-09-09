"""T20 / issue #28's "Compare strategies" slice: ``POST /disclosure/compare``.

Mirrors ``tests/test_api_disclosure.py``'s own style: real core, real
policies, real detector -- only the provider is ever a stub.
"""

from __future__ import annotations

from adaptive_disclosure_gateway.application.contracts import (
    CANONICAL_COMPARISON_ORDER,
    DisclosureApplicationRequest,
)
from adaptive_disclosure_gateway.application.ingestion import normalize_text
from tests.api_support import (
    HR_TEXT,
    NeverCallMeProvider,
    RecordingProvider,
    build_client,
    build_service,
)


def test_compare_never_calls_the_provider():
    client = build_client(build_service(NeverCallMeProvider()))

    response = client.post(
        "/disclosure/compare", json={"text": HR_TEXT, "task": "summarize personnel record"}
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["entries"]) == 5


def test_compare_returns_entries_in_canonical_order():
    client = build_client(build_service(RecordingProvider()))

    response = client.post(
        "/disclosure/compare", json={"text": HR_TEXT, "task": "summarize personnel record"}
    )

    body = response.json()
    assert [entry["strategy"] for entry in body["entries"]] == [
        strategy.value for strategy in CANONICAL_COMPARISON_ORDER
    ]


def test_compare_response_equals_the_direct_service_result():
    provider = RecordingProvider()
    service = build_service(provider)
    client = build_client(service)
    body = {"text": HR_TEXT, "task": "summarize personnel record"}

    direct = service.compare_strategies(
        DisclosureApplicationRequest(content=normalize_text(HR_TEXT), task=body["task"])
    )
    response = client.post("/disclosure/compare", json=body)

    payload = response.json()
    assert len(payload["entries"]) == len(direct.entries)
    for entry_payload, direct_entry in zip(payload["entries"], direct.entries, strict=True):
        assert entry_payload["strategy"] == direct_entry.strategy.value
        assert entry_payload["treatment"] == direct_entry.treatment.value
        assert entry_payload["recommended"] == direct_entry.recommended
        assert entry_payload["unsafe_control_baseline"] == direct_entry.unsafe_control_baseline
        assert entry_payload["external_payload"] == direct_entry.external_payload
        assert entry_payload["payload_byte_count"] == direct_entry.payload_byte_count
    assert payload["governance"]["domain"] == direct.governance.domain
    assert payload["provider_mode"]["provider_class"] == direct.provider_mode.provider_class


def test_compare_body_strategy_field_is_ignored_and_covers_all_five():
    client = build_client(build_service(RecordingProvider()))

    response = client.post(
        "/disclosure/compare",
        json={"text": HR_TEXT, "task": "summarize personnel record", "strategy": "b2"},
    )

    body = response.json()
    assert {entry["strategy"] for entry in body["entries"]} == {"b0", "b1", "b2", "b3", "b4"}


def test_compare_only_direct_baseline_is_marked_unsafe_control_baseline():
    client = build_client(build_service(RecordingProvider()))

    response = client.post(
        "/disclosure/compare", json={"text": HR_TEXT, "task": "summarize personnel record"}
    )

    body = response.json()
    baseline_entries = [e for e in body["entries"] if e["unsafe_control_baseline"]]
    assert len(baseline_entries) == 1
    assert baseline_entries[0]["strategy"] == "b0"


def test_compare_exactly_one_entry_is_recommended():
    client = build_client(build_service(RecordingProvider()))

    response = client.post(
        "/disclosure/compare", json={"text": HR_TEXT, "task": "summarize personnel record"}
    )

    body = response.json()
    recommended_entries = [e for e in body["entries"] if e["recommended"]]
    assert len(recommended_entries) == 1
    assert recommended_entries[0]["strategy"] == "b4"
