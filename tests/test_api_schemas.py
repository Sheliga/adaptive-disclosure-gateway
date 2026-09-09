"""T20 / issue #28, slice 2, absolute rule 4 -- explicit response schemas.
Requirement 11: every response model's field set is pinned against a
literal expected set, so a field silently added to an internal contract
(``application/contracts.py``, ``audit.py``) later cannot auto-appear on
the public HTTP surface without this test failing first.
"""

from __future__ import annotations

from adaptive_disclosure_gateway.api import schemas


def test_health_response_field_sets_are_explicit():
    assert set(schemas.HealthResponse.model_fields) == {
        "status",
        "contract_version",
        "provider",
        "treatments_available",
    }
    assert set(schemas.ProviderHealthModel.model_fields) == {
        "provider_class",
        "model_id",
        "model_snapshot",
        "deterministic_demo_mode",
    }


def test_examples_response_field_sets_are_explicit():
    assert set(schemas.ExamplesResponse.model_fields) == {"contract_version", "examples"}
    assert set(schemas.ExampleSummaryModel.model_fields) == {
        "example_id",
        "title",
        "domain",
        "purpose",
        "task",
        "character_count",
    }


def test_strategies_response_field_sets_are_explicit():
    assert set(schemas.StrategiesResponse.model_fields) == {"contract_version", "strategies"}
    assert set(schemas.StrategyInfoModel.model_fields) == {
        "strategy",
        "treatment_code",
        "recommended",
    }


def test_preview_response_field_sets_are_explicit():
    assert set(schemas.PreviewResponse.model_fields) == {
        "contract_version",
        "summary",
        "external_payload",
        "payload_byte_count",
        "treatment",
        "strategy",
        "governance",
        "provider_mode",
    }
    assert set(schemas.DisclosureSummaryModel.model_fields) == {
        "status",
        "categories",
        "detected_span_count",
        "detected_categories",
    }
    assert set(schemas.CategoryDisclosureSummaryModel.model_fields) == {
        "category",
        "outcome",
        "action",
        "crosses_trust_boundary",
        "occurrence_count",
        "required_for_task",
        "technical_reason",
        "policy_version",
        "policy_restricted",
        "impossible_under_policy",
    }
    assert set(schemas.SafeGovernanceViewModel.model_fields) == {
        "domain",
        "purpose",
        "policy_version",
        "provider_class",
        "requester_role",
        "requested_pseudonym_scope",
    }
    assert set(schemas.ProviderModeModel.model_fields) == {"provider_class"}


def test_execute_response_field_sets_are_explicit():
    assert set(schemas.ExecuteResponse.model_fields) == {
        "contract_version",
        "status",
        "summary",
        "final_answer",
        "provider",
        "reconstruction",
        "treatment",
        "strategy",
        "governance",
        "total_ms",
    }
    assert set(schemas.ProviderStageModel.model_fields) == {
        "called",
        "provider_class",
        "model_id",
        "model_snapshot",
        "decoding_config",
        "transmitted_bytes",
        "response_hash",
        "failed",
        "failure_kind",
    }
    assert set(schemas.ReconstructionStageModel.model_fields) == {
        "attempted",
        "reconstructed_hash",
        "changed_from_provider_response",
    }


def test_error_response_field_sets_are_explicit():
    assert set(schemas.ErrorResponse.model_fields) == {"detail", "kind"}
    assert set(schemas.ValidationErrorResponse.model_fields) == {"detail"}
    assert set(schemas.ValidationErrorItem.model_fields) == {"loc", "type", "msg"}


def test_request_body_field_sets_are_explicit():
    assert set(schemas.DisclosureRequestBody.model_fields) == {
        "text",
        "filename",
        "file_content",
        "example_id",
        "task",
        "strategy",
        "governance",
    }
    assert set(schemas.GovernanceOverridesBody.model_fields) == {
        "purpose",
        "requester_role",
        "requester_id",
        "provider_class",
        "policy_version",
        "requested_pseudonym_scope",
        "session_id",
        "document_id",
        "request_id",
        "domain",
    }


def test_every_response_model_forbids_extra_fields():
    """Every response/request model must declare ``extra="forbid"`` --
    otherwise a caller-supplied or accidentally-passed extra field could
    round-trip through undetected, defeating the point of an explicit field
    set.
    """
    models = [
        schemas.GovernanceOverridesBody,
        schemas.DisclosureRequestBody,
        schemas.ProviderHealthModel,
        schemas.HealthResponse,
        schemas.ExampleSummaryModel,
        schemas.ExamplesResponse,
        schemas.StrategyInfoModel,
        schemas.StrategiesResponse,
        schemas.CategoryDisclosureSummaryModel,
        schemas.DisclosureSummaryModel,
        schemas.SafeGovernanceViewModel,
        schemas.ProviderModeModel,
        schemas.PreviewResponse,
        schemas.ProviderStageModel,
        schemas.ReconstructionStageModel,
        schemas.ExecuteResponse,
        schemas.ErrorResponse,
        schemas.ValidationErrorItem,
        schemas.ValidationErrorResponse,
    ]
    for model in models:
        assert model.model_config.get("extra") == "forbid", model.__name__
