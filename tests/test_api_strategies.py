"""T20 / issue #28, slice 2: ``GET /strategies``. Requirement 13."""

from __future__ import annotations

from tests.api_support import build_client, build_service


def test_strategies_lists_all_five_treatments_plus_the_recommended_default():
    client = build_client(build_service())

    response = client.get("/strategies")

    assert response.status_code == 200
    body = response.json()
    assert body["contract_version"] == "t20-application-api-v1"
    strategies = body["strategies"]
    codes = {entry["strategy"] for entry in strategies}
    assert codes == {"recommended", "b0", "b1", "b2", "b3", "b4"}

    recommended_entries = [entry for entry in strategies if entry["recommended"]]
    assert len(recommended_entries) == 1
    assert recommended_entries[0]["strategy"] == "recommended"
    assert recommended_entries[0]["treatment_code"] == "b4"

    for entry in strategies:
        assert set(entry) == {"strategy", "treatment_code", "recommended"}


def test_strategies_endpoint_executes_nothing():
    """A whole strategies listing must not touch a provider or any content
    -- it is pure discovery data, computed with no request body at all.
    """
    from tests.api_support import NeverCallMeProvider

    client = build_client(build_service(NeverCallMeProvider()))

    response = client.get("/strategies")

    assert response.status_code == 200
