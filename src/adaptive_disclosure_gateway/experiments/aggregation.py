"""Descriptive aggregation for T10's pilot (issue #8): per-treatment
summaries and pairwise B0->B1, B1->B2, B2->B3 and B3->B4 comparisons.

Deliberately descriptive only -- means, rates and counts over the pilot's
small N, never a significance test or confidence interval
(docs/experimental-design.md's "no sophisticated statistical inference at
pilot N" rule, and the T10 brief's explicit prohibition on advanced
statistical-significance testing).
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Literal

from .case_result import CaseResult
from .scoring.detector_scoring import DetectorAggregateScore, aggregate_detector_scores

_UTILITY_RANK = {"not_answerable": 0, "indeterminate": 1, "not_applicable": 2, "answerable": 3}


def _safe_mean(values: list[float]) -> float | None:
    return mean(values) if values else None


def _safe_rate(numerator: int, denominator: int) -> float | None:
    return (numerator / denominator) if denominator else None


@dataclass(frozen=True)
class TreatmentSummary:
    treatment_code: str
    case_count: int
    blocked_count: int
    conformant_count: int
    nonconformant_count: int
    scored_span_count: int
    conformant_rate: float | None
    not_required_total: int
    not_required_transmitted: int
    unnecessary_disclosure_rate: float | None
    utility_answerable_count: int
    utility_scored_count: int
    utility_answerable_rate: float | None
    reconstruction_correct_count: int
    reconstruction_scored_count: int
    mean_treatment_ms: float | None
    mean_provider_ms: float | None
    mean_pipeline_total_ms: float | None
    mean_payload_bytes: float | None
    mean_total_request_bytes: float | None
    policy_restricted_count: int
    impossible_under_policy_count: int
    policy_block_count: int
    ordinary_utility_failure_count: int
    provider_failure_count: int
    mean_cpu_time_ms: float | None
    mean_peak_memory_bytes: float | None
    resource_measurement_scope: str | None
    detector: DetectorAggregateScore


def summarize_treatment(results: list[CaseResult]) -> TreatmentSummary:
    treatment_codes = {r.identity.treatment_code for r in results}
    treatment_code = next(iter(treatment_codes)) if len(treatment_codes) == 1 else "mixed"

    blocked = sum(1 for r in results if r.score.outcomes.blocked)
    conformant = sum(r.score.conformance.conformant_count for r in results)
    nonconformant = sum(r.score.conformance.nonconformant_count for r in results)
    scored = conformant + nonconformant

    not_required_total = sum(r.score.unnecessary_disclosure.not_required_total for r in results)
    not_required_transmitted = sum(
        r.score.unnecessary_disclosure.not_required_transmitted for r in results
    )

    utility_scores = [
        r.score.utility.overall for r in results if r.score.utility.overall != "not_applicable"
    ]
    utility_answerable = sum(1 for u in utility_scores if u == "answerable")

    reconstruction_entries = [
        entry
        for r in results
        for entry in r.score.reconstruction.by_category
        if entry.outcome != "not_applicable"
    ]
    reconstruction_correct = sum(1 for e in reconstruction_entries if e.outcome == "correct")

    treatment_ms = [
        r.case_execution.stage_timings.treatment_ms
        for r in results
        if r.case_execution.stage_timings.treatment_ms is not None
    ]
    provider_ms = [
        r.case_execution.provider_metrics.latency_ms
        for r in results
        if r.case_execution.provider_metrics is not None
    ]
    pipeline_ms = [
        r.case_execution.stage_timings.pipeline_total_ms
        for r in results
        if r.case_execution.stage_timings.pipeline_total_ms is not None
    ]
    payload_bytes = [
        r.case_execution.provider_metrics.payload_bytes
        for r in results
        if r.case_execution.provider_metrics is not None
    ]
    total_request_bytes = [
        r.case_execution.provider_metrics.total_request_bytes
        for r in results
        if r.case_execution.provider_metrics is not None
    ]

    cpu_times_ms = [r.case_execution.resource_metrics.cpu_time_ms for r in results]
    peak_memory_bytes = [
        float(r.case_execution.resource_metrics.peak_memory_bytes) for r in results
    ]
    resource_scopes = {r.case_execution.resource_metrics.measurement_scope for r in results}
    resource_measurement_scope = next(iter(resource_scopes)) if len(resource_scopes) == 1 else None

    detector_aggregate = aggregate_detector_scores([r.score.detector for r in results])

    return TreatmentSummary(
        treatment_code=treatment_code,
        case_count=len(results),
        blocked_count=blocked,
        conformant_count=conformant,
        nonconformant_count=nonconformant,
        scored_span_count=scored,
        conformant_rate=_safe_rate(conformant, scored),
        not_required_total=not_required_total,
        not_required_transmitted=not_required_transmitted,
        unnecessary_disclosure_rate=_safe_rate(not_required_transmitted, not_required_total),
        utility_answerable_count=utility_answerable,
        utility_scored_count=len(utility_scores),
        utility_answerable_rate=_safe_rate(utility_answerable, len(utility_scores)),
        reconstruction_correct_count=reconstruction_correct,
        reconstruction_scored_count=len(reconstruction_entries),
        mean_treatment_ms=_safe_mean(treatment_ms),
        mean_provider_ms=_safe_mean(provider_ms),
        mean_pipeline_total_ms=_safe_mean(pipeline_ms),
        mean_payload_bytes=_safe_mean([float(b) for b in payload_bytes]),
        mean_total_request_bytes=_safe_mean([float(b) for b in total_request_bytes]),
        policy_restricted_count=sum(1 for r in results if r.score.outcomes.policy_restricted),
        impossible_under_policy_count=sum(
            1 for r in results if r.score.outcomes.impossible_under_policy
        ),
        policy_block_count=sum(1 for r in results if r.score.outcomes.policy_block),
        ordinary_utility_failure_count=sum(1 for r in results if r.score.ordinary_utility_failure),
        provider_failure_count=sum(1 for r in results if r.score.outcomes.provider_failure),
        mean_cpu_time_ms=_safe_mean(cpu_times_ms),
        mean_peak_memory_bytes=_safe_mean(peak_memory_bytes),
        resource_measurement_scope=resource_measurement_scope,
        detector=detector_aggregate,
    )


@dataclass(frozen=True)
class PairwiseSummary:
    from_treatment: str
    to_treatment: str
    case_count: int
    conformant_rate_from: float | None
    conformant_rate_to: float | None
    unnecessary_disclosure_rate_from: float | None
    unnecessary_disclosure_rate_to: float | None
    utility_answerable_rate_from: float | None
    utility_answerable_rate_to: float | None
    mean_treatment_ms_from: float | None
    mean_treatment_ms_to: float | None
    mean_payload_bytes_from: float | None
    mean_payload_bytes_to: float | None


def _matched_pairs(
    from_results: list[CaseResult], to_results: list[CaseResult]
) -> list[tuple[CaseResult, CaseResult]]:
    by_case_to = {r.identity.case_id: r for r in to_results}
    return [
        (r, by_case_to[r.identity.case_id])
        for r in from_results
        if r.identity.case_id in by_case_to
    ]


def summarize_pairwise(
    from_results: list[CaseResult], to_results: list[CaseResult]
) -> PairwiseSummary:
    """Descriptive from->to summary over cases present in *both* lists
    (matched by ``case_id``). Never a cartesian product, never inferential
    statistics -- just the two treatments' own independently-computed
    per-treatment rates placed side by side.
    """
    pairs = _matched_pairs(from_results, to_results)
    from_side = [pair[0] for pair in pairs]
    to_side = [pair[1] for pair in pairs]
    from_summary = summarize_treatment(from_side) if from_side else None
    to_summary = summarize_treatment(to_side) if to_side else None

    from_code = from_results[0].identity.treatment_code if from_results else "unknown"
    to_code = to_results[0].identity.treatment_code if to_results else "unknown"

    return PairwiseSummary(
        from_treatment=from_code,
        to_treatment=to_code,
        case_count=len(pairs),
        conformant_rate_from=from_summary.conformant_rate if from_summary else None,
        conformant_rate_to=to_summary.conformant_rate if to_summary else None,
        unnecessary_disclosure_rate_from=(
            from_summary.unnecessary_disclosure_rate if from_summary else None
        ),
        unnecessary_disclosure_rate_to=(
            to_summary.unnecessary_disclosure_rate if to_summary else None
        ),
        utility_answerable_rate_from=from_summary.utility_answerable_rate if from_summary else None,
        utility_answerable_rate_to=to_summary.utility_answerable_rate if to_summary else None,
        mean_treatment_ms_from=from_summary.mean_treatment_ms if from_summary else None,
        mean_treatment_ms_to=to_summary.mean_treatment_ms if to_summary else None,
        mean_payload_bytes_from=from_summary.mean_payload_bytes if from_summary else None,
        mean_payload_bytes_to=to_summary.mean_payload_bytes if to_summary else None,
    )


ExposureDirection = Literal["b4_less", "b4_more", "same", "incomparable"]
UtilityDirection = Literal["b4_worse", "b4_better", "same", "incomparable"]


@dataclass(frozen=True)
class B3ToB4CaseComparison:
    case_id: str
    same_action_profile: bool
    policy_restricted: bool
    impossible_under_policy: bool
    hard_block_by_b4_not_b3: bool
    exposure_direction: ExposureDirection
    utility_direction: UtilityDirection


@dataclass(frozen=True)
class B3ToB4Summary:
    cases: tuple[B3ToB4CaseComparison, ...]
    same_action_profile_count: int
    policy_restricted_count: int
    impossible_under_policy_count: int
    hard_block_count: int


def _exposure_rank_sum(result: CaseResult) -> int | None:
    ranks = [s.level_rank for s in result.score.exposure.spans if s.level_rank is not None]
    if len(ranks) != len(result.score.exposure.spans):
        return None  # a block/unscorable span makes the whole case incomparable
    return sum(ranks)


def summarize_b3_to_b4(b3_results: list[CaseResult], b4_results: list[CaseResult]) -> B3ToB4Summary:
    pairs = _matched_pairs(b3_results, b4_results)
    comparisons: list[B3ToB4CaseComparison] = []

    for b3, b4 in pairs:
        b3_actions = [s.resolved_action for s in b3.score.conformance.spans]
        b4_actions = [s.resolved_action for s in b4.score.conformance.spans]
        same_actions = b3_actions == b4_actions

        b3_rank = _exposure_rank_sum(b3)
        b4_rank = _exposure_rank_sum(b4)
        if b3_rank is None or b4_rank is None:
            exposure_direction: ExposureDirection = "incomparable"
        elif b4_rank < b3_rank:
            exposure_direction = "b4_less"
        elif b4_rank > b3_rank:
            exposure_direction = "b4_more"
        else:
            exposure_direction = "same"

        b3_utility = b3.score.utility.overall
        b4_utility = b4.score.utility.overall
        if b3_utility == "not_applicable" or b4_utility == "not_applicable":
            utility_direction: UtilityDirection = "incomparable"
        elif _UTILITY_RANK[b4_utility] < _UTILITY_RANK[b3_utility]:
            utility_direction = "b4_worse"
        elif _UTILITY_RANK[b4_utility] > _UTILITY_RANK[b3_utility]:
            utility_direction = "b4_better"
        else:
            utility_direction = "same"

        comparisons.append(
            B3ToB4CaseComparison(
                case_id=b3.identity.case_id,
                same_action_profile=same_actions,
                policy_restricted=b4.score.outcomes.policy_restricted,
                impossible_under_policy=b4.score.outcomes.impossible_under_policy,
                hard_block_by_b4_not_b3=(
                    b4.score.outcomes.policy_block and not b3.score.outcomes.blocked
                ),
                exposure_direction=exposure_direction,
                utility_direction=utility_direction,
            )
        )

    return B3ToB4Summary(
        cases=tuple(comparisons),
        same_action_profile_count=sum(1 for c in comparisons if c.same_action_profile),
        policy_restricted_count=sum(1 for c in comparisons if c.policy_restricted),
        impossible_under_policy_count=sum(1 for c in comparisons if c.impossible_under_policy),
        hard_block_count=sum(1 for c in comparisons if c.hard_block_by_b4_not_b3),
    )
