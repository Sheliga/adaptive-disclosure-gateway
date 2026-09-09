"""T20 / issue #28, slice 2: ``GET /examples``. Requirement 2."""

from __future__ import annotations

from tests.api_support import build_client, build_service


def test_examples_returns_the_prepared_hr_examples():
    client = build_client(build_service())

    response = client.get("/examples")

    assert response.status_code == 200
    body = response.json()
    assert body["contract_version"] == "t20-application-api-v1"
    example_ids = {example["example_id"] for example in body["examples"]}
    assert len(body["examples"]) == 13
    assert "hr_team_summary_001" in example_ids


def test_examples_carries_no_oracle_or_ground_truth_field():
    client = build_client(build_service())

    response = client.get("/examples")

    body = response.json()
    example = body["examples"][0]
    assert set(example) == {"example_id", "title", "domain", "purpose", "task", "character_count"}
    raw = response.text
    assert "oracle" not in raw
    assert "expected_spans" not in raw
    assert "expected_answer" not in raw
