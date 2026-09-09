"""T20 / issue #28, slice 2: ``GET /health``. Requirement 1."""

from __future__ import annotations

from tests.api_support import NeverCallMeProvider, RecordingProvider, build_client, build_service


def test_health_reports_fake_provider_as_deterministic_demo_mode():
    from adaptive_disclosure_gateway.providers import FakeProvider

    client = build_client(build_service(FakeProvider()))

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["contract_version"] == "t20-application-api-v1"
    assert body["provider"]["provider_class"] == "fake"
    assert body["provider"]["deterministic_demo_mode"] is True
    assert set(body["treatments_available"]) == {"b0", "b1", "b2", "b3", "b4"}


def test_health_reports_false_deterministic_demo_mode_for_a_non_fake_provider():
    client = build_client(build_service(RecordingProvider()))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["provider"]["deterministic_demo_mode"] is False


def test_health_never_calls_the_provider():
    client = build_client(build_service(NeverCallMeProvider()))

    response = client.get("/health")

    assert response.status_code == 200
