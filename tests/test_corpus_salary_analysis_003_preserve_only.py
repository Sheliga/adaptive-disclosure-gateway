"""Single-case regression for ``hr_salary_analysis_003`` (T09 / issue #4,
Phase A -- PR #31 review round 5).

This test is deliberately scoped to one case, not a corpus-wide invariant.
A prior round (commit 1907ffd) introduced
``tests/test_corpus_generalization_preserves_utility.py``, which asserted a
*global* rule that generalizing any ``required`` span must never make its
case's ``expected_answer`` unverifiable. That rule was removed: it silently
conflated two independent oracles that ``corpus/hr/v1/SCHEMA.md`` and
``docs/experimental-design.md`` deliberately keep separate --
``expected_actions`` (conformance: is an action disclosure-acceptable under
policy/task-necessity) and ``expected_answer`` (utility: does the resulting
representation still answer the task). A conformant action is allowed to
destroy utility; measuring exactly that trade-off across B0-B4 is T10's job,
not something the corpus should define away by construction.

This test does **not** claim that every acceptable action in every case's
``expected_actions`` preserves ``expected_answer``'s utility in general --
it is not a reinstatement of the deleted global invariant under a new name.
It pins something narrower and case-specific: in ``hr_salary_analysis_003``,
the task itself is defined as "does this salary clear a specific numeric
floor". That framing makes ``preserve`` the only representation of the
salary span that can answer the question at all -- a generalized band that
straddles the floor cannot say whether the (unknown, banded) value is above
or below it. ``generalize`` is excluded from this case's
``expected_actions`` for that reason, and this test exists to catch silent
drift away from it (e.g. someone re-adding ``generalize`` here because it
"should" be acceptable by the deleted global rule's logic).

If ``NumericBandStrategy``'s configuration (band width, floor, or salary
figure) ever changes such that the generalized band for this case's salary
value no longer straddles the reference floor, the second assertion below
fails, which is the correct signal that this case's annotation needs
re-examination -- always via a new corpus version
(``corpus/hr/v1+1/...``), per the freeze rule in
``corpus/hr/v1/README.md``. v1 itself is never edited in place.
"""

from __future__ import annotations

import re
from pathlib import Path

from adaptive_disclosure_gateway.corpus import load_corpus
from adaptive_disclosure_gateway.domain import DisclosureAction
from adaptive_disclosure_gateway.transformations.generalization import generalize

REPO_ROOT = Path(__file__).parents[1]
REAL_CORPUS_DIR = REPO_ROOT / "corpus" / "hr" / "v1" / "cases"
SAMPLE_ID = "hr_salary_analysis_003"

# Matches the generalized "<prefix><lower>-<upper>" shape produced by
# NumericBandStrategy.generalize (e.g. "R$ 0-5000") -- generalize() is what
# produces this string; this pattern only extracts its two bounds, never a
# raw span value.
_GENERALIZED_BAND = re.compile(r"(-?\d+(?:\.\d+)?)-(-?\d+(?:\.\d+)?)")

# The corpus's literal reference-floor line shape (see SCHEMA.md's
# "Task-necessity/answer coherence" section).
_REFERENCE_FLOOR_LINE = re.compile(r"Reference minimum wage floor:\s*R\$\s*([\d.]+)")


def _load_case():
    cases = load_corpus(REAL_CORPUS_DIR)
    for case in cases:
        if case.input.sample_id == SAMPLE_ID:
            return case
    raise AssertionError(f"expected corpus case {SAMPLE_ID!r} to exist")


def _salary_span(case):
    salary_spans = [span for span in case.oracle.expected_spans if span.category == "salary"]
    assert len(salary_spans) == 1, (
        f"{SAMPLE_ID}: expected exactly one salary span, found {len(salary_spans)}"
    )
    return salary_spans[0]


def test_salary_span_expected_actions_is_preserve_only():
    """Pins annotation (1): ``expected_actions`` for the salary span is
    exactly ``[preserve]`` -- ``generalize`` is not among the acceptable
    actions for this case."""
    case = _load_case()
    span = _salary_span(case)

    assert span.expected_actions == [DisclosureAction.PRESERVE], (
        f"{SAMPLE_ID}: salary span expected_actions changed from [preserve] "
        f"to {span.expected_actions!r} -- if generalize was re-added, confirm "
        "the premise this case relies on (assertion 2 in this module) still "
        "holds before treating that as a valid annotation, and make any real "
        "change in a new corpus version, never by editing v1 in place"
    )


def test_generalized_salary_band_still_straddles_the_reference_floor():
    """Pins annotation (2): the reason ``preserve`` is the only acceptable
    action still holds -- generalizing this case's salary value produces a
    band that straddles (does not clear) the case's own reference minimum
    wage floor, so a generalized representation cannot answer "above the
    floor or not". If this ever stops being true, the frozen annotation's
    justification no longer applies and hr_salary_analysis_003 needs review
    in a new corpus version (never an in-place edit of v1)."""
    case = _load_case()
    span = _salary_span(case)

    floor_match = _REFERENCE_FLOOR_LINE.search(case.input.text)
    assert floor_match is not None, (
        f"{SAMPLE_ID}: expected a 'Reference minimum wage floor:' line in input.text"
    )
    floor = float(floor_match.group(1))

    generalized = generalize(span.category, span.value)
    band_match = _GENERALIZED_BAND.search(generalized)
    assert band_match is not None, (
        f"{SAMPLE_ID}: generalize() for category {span.category!r} did not "
        "produce a lower-upper band"
    )
    lower, upper = float(band_match.group(1)), float(band_match.group(2))

    assert lower < floor < upper, (
        f"{SAMPLE_ID}: the frozen preserve-only annotation for the "
        f"{span.category!r} span assumed the generalized band "
        f"[{lower:g}, {upper:g}) straddles the reference floor {floor:g} -- "
        "that premise no longer holds, so this annotation's justification "
        "is stale. This must be revisited in a new corpus version "
        "(corpus/hr/v1+1/...), never by editing frozen v1 in place."
    )
