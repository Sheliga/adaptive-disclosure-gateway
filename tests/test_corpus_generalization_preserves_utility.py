"""GENERALIZE-preserves-utility invariant for the frozen HR pilot corpus
(T09 / issue #4, Phase A -- PR #31 review round 4).

A span annotated ``task_necessity: required`` with ``generalize`` among its
``expected_actions`` asserts that generalizing the value still leaves enough
information to verify the case's ``expected_answer``. For a numeric category
that is not automatic: ``transformations/generalization.py``'s
``NumericBandStrategy`` bins the value into a fixed-width, half-open
``[lower, upper)`` band, and several cases' ``expected_answer`` asserts a
containment property against a reference band or wage floor stated literally
in ``input.text`` (see ``tests/test_corpus_answer_grounded_in_input.py``). If
the generated band straddles that reference boundary, the containment
property becomes undecidable from the band alone -- ``generalize`` reads as
an acceptable action on paper but actually destroys the information the
``expected_answer`` depends on, making that annotation a coherence defect
rather than a real oracle.

This check is deliberately narrow and specific to this controlled,
frozen corpus's two known reference-line shapes (``Reference band for <X>:
R$ <A> to R$ <B>`` and ``Reference minimum wage floor: R$ <F>``) rather than
a general-purpose natural-language answer verifier: v1 has 13 fixed cases and
a generic containment checker would be unnecessary machinery that is itself
unverifiable.
"""

from __future__ import annotations

import re
from pathlib import Path

from adaptive_disclosure_gateway.corpus import TaskNecessity, load_corpus
from adaptive_disclosure_gateway.domain import DisclosureAction
from adaptive_disclosure_gateway.transformations.generalization import (
    generalize,
    is_configured,
)

REPO_ROOT = Path(__file__).parents[1]
REAL_CORPUS_DIR = REPO_ROOT / "corpus" / "hr" / "v1" / "cases"

# Matches the generalized "<prefix><lower>-<upper>" shape produced by
# NumericBandStrategy.generalize (e.g. "R$ 15000-20000"), never the raw span
# value -- generalize() is what produces this string, this pattern only
# extracts its two bounds.
_GENERALIZED_BAND = re.compile(r"(-?\d+(?:\.\d+)?)-(-?\d+(?:\.\d+)?)")

# The corpus's two literal reference-line shapes (see module docstring).
_REFERENCE_BAND_LINE = re.compile(r"Reference band for [^:]+:\s*R\$\s*([\d.]+) to R\$\s*([\d.]+)")
_REFERENCE_FLOOR_LINE = re.compile(r"Reference minimum wage floor:\s*R\$\s*([\d.]+)")


def _parse_generalized_band(generalized: str) -> tuple[float, float]:
    match = _GENERALIZED_BAND.search(generalized)
    assert match is not None, "generalize() output did not contain a lower-upper band"
    return float(match.group(1)), float(match.group(2))


def test_generalize_never_makes_a_required_spans_expected_answer_unverifiable():
    cases = load_corpus(REAL_CORPUS_DIR)
    assert cases, "expected at least one corpus case to check"

    failures = []
    checked = 0
    for case in cases:
        text = case.input.text
        band_match = _REFERENCE_BAND_LINE.search(text)
        floor_match = _REFERENCE_FLOOR_LINE.search(text)
        if band_match is None and floor_match is None:
            continue  # no reference-based property in this case to check against

        for span in case.oracle.expected_spans:
            if span.task_necessity is not TaskNecessity.REQUIRED:
                continue
            if DisclosureAction.GENERALIZE not in span.expected_actions:
                continue
            if not is_configured(span.category):
                continue

            lower, upper = _parse_generalized_band(generalize(span.category, span.value))
            checked += 1

            if band_match is not None:
                ref_lower, ref_upper = float(band_match.group(1)), float(band_match.group(2))
                if not (lower >= ref_lower and upper <= ref_upper):
                    failures.append(
                        f"{case.input.sample_id}: {span.category} generalized band "
                        f"[{lower:g}, {upper:g}) is not contained in the reference band "
                        f"[{ref_lower:g}, {ref_upper:g}]"
                    )
            else:
                ref_floor = float(floor_match.group(1))
                if not lower >= ref_floor:
                    failures.append(
                        f"{case.input.sample_id}: {span.category} generalized band "
                        f"[{lower:g}, {upper:g}) is not entirely above the reference "
                        f"floor {ref_floor:g}"
                    )

    assert checked > 0, "expected at least one required+generalize span with a reference line"
    assert not failures, (
        "generalize is listed among expected_actions for a required span, but the "
        "generated band destroys the information expected_answer depends on -- "
        "the resulting band is unverifiable against the case's own reference "
        "line: " + "; ".join(failures)
    )
