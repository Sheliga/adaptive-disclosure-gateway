"""Builds the application layer's presentational ``DisclosureSummary`` from
a real ``pipeline.DisclosureDecision`` -- the shared decision phase both
``preview`` and ``execute`` run through (T20 / issue #28, slice 1).

``crosses_trust_boundary`` on each ``CategoryDisclosureSummary`` is a
presentational boolean for the UI's "what stays local vs. what is sent"
step. It is explicitly NOT the T10 scientific exposure metric
(``experiments/scoring/exposure.py``), which requires the corpus oracle and
stays exactly where it is -- this module has no dependency on
``experiments`` or the oracle at all.
"""

from __future__ import annotations

from adaptive_disclosure_gateway.application.contracts import (
    CategoryDisclosureSummary,
    DisclosureOutcome,
    DisclosureSummary,
)
from adaptive_disclosure_gateway.domain import DisclosureAction
from adaptive_disclosure_gateway.pipeline import DisclosureDecision

# Explicit, exhaustive mapping over every DisclosureAction member -- pinned
# by tests/test_application_summaries.py::test_every_disclosure_action_is_covered_by_the_outcome_mapping
# -- so a future action added to DisclosureAction cannot silently default to
# "does not cross the trust boundary" just by being absent here.
#
# TASK_DEPENDENT is mapped to None deliberately, not omitted: it is a
# policy-authoring placeholder (see policies.PolicyRule.default) that
# PolicyRepository.decide() always resolves to a concrete action before a
# PolicyDecision/ActionDecision reaches any treatment's DisclosureResult
# (see policies.py's `decide()`). A *resolved* TASK_DEPENDENT action
# reaching this boundary is therefore a defect upstream, not a valid case to
# render -- it fails closed by raising in _outcome_for_action below, rather
# than guessing a mapping for something that should never happen.
_OUTCOME_BY_ACTION: dict[DisclosureAction, tuple[DisclosureOutcome, bool] | None] = {
    DisclosureAction.PRESERVE: (DisclosureOutcome.PRESERVED, True),
    DisclosureAction.PSEUDONYMIZE: (DisclosureOutcome.PSEUDONYMIZED, True),
    DisclosureAction.GENERALIZE: (DisclosureOutcome.GENERALIZED, True),
    DisclosureAction.REMOVE: (DisclosureOutcome.REMOVED, False),
    DisclosureAction.BLOCK_REQUEST: (DisclosureOutcome.BLOCKED, False),
    DisclosureAction.TASK_DEPENDENT: None,
}


def _outcome_for_action(action: DisclosureAction) -> tuple[DisclosureOutcome, bool]:
    mapped = _OUTCOME_BY_ACTION[action]
    if mapped is None:
        raise ValueError(
            f"unresolved {action.name} action reached the application summary boundary -- "
            "every action reaching here must already be a concrete, policy-resolved action"
        )
    return mapped


def build_disclosure_summary(decision: DisclosureDecision) -> DisclosureSummary:
    """Derive a ``DisclosureSummary`` from ``decision``.

    Per-category ``occurrence_count`` primarily counts
    ``DisclosureResult.transformations`` entries for that category (accurate
    whenever the request was allowed far enough to produce them); a category
    that never got that far (its own detected occurrences forced a block
    before any transformation was produced) falls back to counting
    ``decision.spans`` of that category instead, so a blocked category never
    silently reports zero occurrences when it was in fact detected in
    ``request.text``.
    """
    result = decision.result
    spans = decision.spans

    span_counts_by_category: dict[str, int] = {}
    for span in spans:
        span_counts_by_category[span.category] = span_counts_by_category.get(span.category, 0) + 1

    transformation_counts_by_category: dict[str, int] = {}
    for transformation in result.transformations:
        transformation_counts_by_category[transformation.category] = (
            transformation_counts_by_category.get(transformation.category, 0) + 1
        )

    categories = []
    for policy_decision in result.decisions:
        outcome, crosses = _outcome_for_action(policy_decision.action)
        occurrence_count = transformation_counts_by_category.get(policy_decision.category)
        if occurrence_count is None:
            occurrence_count = span_counts_by_category.get(policy_decision.category, 0)

        categories.append(
            CategoryDisclosureSummary(
                category=policy_decision.category,
                outcome=outcome,
                action=policy_decision.action,
                crosses_trust_boundary=crosses,
                occurrence_count=occurrence_count,
                required_for_task=policy_decision.task_required,
                technical_reason=policy_decision.reason,
                policy_version=policy_decision.policy_version,
                policy_restricted=policy_decision.policy_restricted,
                impossible_under_policy=policy_decision.impossible_under_policy,
            )
        )

    return DisclosureSummary(
        status=result.status,
        categories=tuple(categories),
        detected_span_count=len(spans),
        detected_categories=tuple(sorted({span.category for span in spans})),
    )
