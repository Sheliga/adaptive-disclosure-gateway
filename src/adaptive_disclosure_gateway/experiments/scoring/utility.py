"""Utility scoring (T10 / issue #8).

Scored against ``CaseOracle.expected_answer``/``answer_depends_on_categories``
-- the utility oracle -- deliberately independent of ``expected_actions``
(the conformance oracle scored in ``conformance.py``). See
``corpus/hr/v1/SCHEMA.md``'s "Conformance and utility are independent
oracles": an action can be a fully conformant member of ``expected_actions``
and still destroy the information ``expected_answer`` depends on (the
documented ``hr_department_aggregation_003``/``hr_salary_analysis_003``
GENERALIZE-band case), and the reverse also holds -- a nonconformant action
can still happen to preserve enough information to answer.

Pilot-scoped measurement choice, documented here because it drives every
utility outcome this module produces: ``FakeProvider`` never computes a
real answer (it returns a fixed acknowledgement string -- see
``providers/fake.py``), so utility cannot be scored from the provider's
*response* text at all in this pilot. Instead this module scores whether
the *disclosure-controlled payload* retains enough information, per
category, for a competent provider to have answered -- an information-
sufficiency proxy, not a literal-answer-correctness check. This must be
re-scored against real provider output once T22's real-provider work lands;
until then this proxy is the only thing FakeProvider makes measurable, and
docs/experimental-design.md's own provider-strategy section already
anticipates this split (FakeProvider valid for the pilot, a real provider
required before authoritative utility claims).

GENERALIZE decidability rule (SCHEMA.md's documented pattern, generalized
rather than special-cased to one sample_id): a generalized numeric band is
"decidable" against a reference figure stated elsewhere in ``input.text``
(outside any detected span) only if the reference falls strictly outside
the band -- if it falls inside, the band alone cannot tell whether the
original value was above or below the reference, exactly the ambiguity
``corpus/hr/v1/SCHEMA.md`` documents for ``hr_salary_analysis_003`` and
``hr_department_aggregation_003``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from adaptive_disclosure_gateway.corpus.case_input import CorpusCaseInput
from adaptive_disclosure_gateway.corpus.oracle import CaseOracle
from adaptive_disclosure_gateway.domain import DisclosureAction, DisclosureResult, Treatment

from .span_matching import resolve_span_transformations

UtilityOutcome = Literal["answerable", "not_answerable", "indeterminate", "not_applicable"]

_AMOUNT_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")
_BAND_PATTERN = re.compile(r"(-?\d+)\s*-\s*(-?\d+)\s*$")


@dataclass(frozen=True)
class CategoryUtility:
    category: str
    outcome: UtilityOutcome
    reason: str


@dataclass(frozen=True)
class UtilityScore:
    overall: UtilityOutcome
    by_category: tuple[CategoryUtility, ...]


def _reference_values(text: str, exclude_spans: list[tuple[int, int]]) -> list[float]:
    """Numeric amounts in ``text`` that fall entirely outside every detected
    span's own offsets -- candidate reference figures (SCHEMA.md's "appended
    line the detector does not match against any of the five frozen
    categories").
    """
    values: list[float] = []
    for match in _AMOUNT_PATTERN.finditer(text):
        start, end = match.span()
        if any(span_start <= start and end <= span_end for span_start, span_end in exclude_spans):
            continue
        values.append(float(match.group()))
    return values


def _band_is_decidable(transformed: str, references: list[float]) -> bool:
    match = _BAND_PATTERN.search(transformed)
    if not match:
        return False
    lower, upper = float(match.group(1)), float(match.group(2))
    return all(reference < lower or reference >= upper for reference in references)


def score_utility(
    case_input: CorpusCaseInput,
    oracle: CaseOracle,
    result: DisclosureResult,
    treatment: Treatment,
) -> UtilityScore:
    if oracle.expected_block_request:
        # A case whose oracle expects a block never has an expected_answer
        # to score at all (CaseOracle's own validator forbids the
        # combination) -- utility is not applicable, not a failure.
        return UtilityScore(overall="not_applicable", by_category=())

    depends_on = oracle.answer_depends_on_categories or []

    if result.status == "blocked":
        # The oracle did not expect this case to block, but this run
        # produced one anyway: nothing was transmitted, so every dependent
        # category is unanswerable -- and this is reported distinctly
        # ("unexpected_block"), not folded into "removed"/"pseudonymized".
        by_category = tuple(
            CategoryUtility(category=category, outcome="not_answerable", reason="unexpected_block")
            for category in depends_on
        )
        return UtilityScore(
            overall="not_answerable" if by_category else "not_applicable", by_category=by_category
        )

    if treatment is Treatment.DIRECT:
        by_category = tuple(
            CategoryUtility(category=category, outcome="answerable", reason="direct_disclosure")
            for category in depends_on
        )
        return UtilityScore(
            overall="answerable" if by_category else "not_applicable", by_category=by_category
        )

    transformations = resolve_span_transformations(oracle, result, treatment)
    exclude_spans = [(span.start, span.end) for span in oracle.expected_spans]
    references = _reference_values(case_input.text, exclude_spans)
    reconstructable_categories = {
        expectation.category
        for expectation in oracle.reconstruction
        if expectation.expected_reconstructable
    }

    by_category_transformations: dict[str, list] = {}
    for span, transformation in zip(oracle.expected_spans, transformations):
        by_category_transformations.setdefault(span.category, []).append(transformation)

    category_scores: list[CategoryUtility] = []
    for category in depends_on:
        entries = by_category_transformations.get(category, [])
        if not entries or any(entry is None for entry in entries):
            category_scores.append(
                CategoryUtility(category=category, outcome="not_answerable", reason="unscorable")
            )
            continue

        outcomes: list[tuple[str, str]] = []
        for transformation in entries:
            action = transformation.action
            if action is DisclosureAction.PRESERVE:
                outcomes.append(("answerable", "preserved"))
            elif action is DisclosureAction.GENERALIZE:
                decidable = _band_is_decidable(transformation.transformed or "", references)
                outcomes.append(
                    ("answerable", "generalized_band_decidable")
                    if decidable
                    else ("indeterminate", "generalized_band_ambiguous")
                )
            elif action is DisclosureAction.PSEUDONYMIZE:
                if category in reconstructable_categories and result.reconstruction_required:
                    outcomes.append(("answerable", "pseudonymized_but_reconstructable"))
                else:
                    outcomes.append(("not_answerable", "pseudonymized_not_reconstructable"))
            elif action is DisclosureAction.REMOVE:
                outcomes.append(("not_answerable", "removed"))
            else:
                outcomes.append(("not_answerable", "unscorable_action"))

        if any(outcome == "not_answerable" for outcome, _ in outcomes):
            final: UtilityOutcome = "not_answerable"
        elif any(outcome == "indeterminate" for outcome, _ in outcomes):
            final = "indeterminate"
        else:
            final = "answerable"
        reason = ";".join(sorted({reason for _, reason in outcomes}))
        category_scores.append(CategoryUtility(category=category, outcome=final, reason=reason))

    if not category_scores:
        overall: UtilityOutcome = "not_applicable"
    elif any(c.outcome == "not_answerable" for c in category_scores):
        overall = "not_answerable"
    elif any(c.outcome == "indeterminate" for c in category_scores):
        overall = "indeterminate"
    else:
        overall = "answerable"

    return UtilityScore(overall=overall, by_category=tuple(category_scores))
