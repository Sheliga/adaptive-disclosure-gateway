"""Utility-oracle grounding for the frozen HR pilot corpus (T09 / issue #4,
Phase A -- PR #31 review round 2).

An ``expected_answer`` is the objectively-verifiable property a correct
treatment's output must satisfy. Before this fix, several cases'
``expected_answer`` cited a compensation band, department policy or minimum
wage floor (e.g. "the standard compensation band for their department",
"Finance department policy", "the minimum wage floor", or a specific
``R$ 5000-10000``-shaped band) that exists nowhere in ``input.text`` --
either it is only available as tacit knowledge, or it happens to match
``transformations/generalization.py``'s ``NumericBandStrategy`` bucket
boundaries, which is a B1/B2-only implementation detail, not common input
available to every treatment B0-B4. Either way, that ground truth cannot be
objectively checked from what a treatment actually received, which
invalidates it as a utility oracle.

This mirrors ``tests/test_corpus_span_consistency.py``'s two-part pattern:
a real-corpus check, plus a synthetic case proving the extraction/
containment helper actually rejects a genuinely ungrounded answer (so a
passing real-corpus check means something).
"""

from __future__ import annotations

import re
from pathlib import Path

from adaptive_disclosure_gateway.corpus import load_corpus

REPO_ROOT = Path(__file__).parents[1]
REAL_CORPUS_DIR = REPO_ROOT / "corpus" / "hr" / "v1" / "cases"

# Every monetary figure this corpus's expected_answer values ever cite is a
# BRL amount formatted "R$ <digits>[.<digits>]" (the same format the corpus
# uses in input.text). Extracting these and checking each one is a verbatim
# substring of input.text is a mechanical, real check: an answer that cites
# a band boundary or floor invented outside the input (rather than restated
# from it) will name a figure absent from input.text. The pattern
# deliberately stops at the decimal point group -- not "[\d.,]+" -- so a
# trailing list comma (e.g. "R$ 15800.00, R$ 6100.00") is never folded into
# the extracted amount.
_MONEY_PATTERN = re.compile(r"R\$\s?\d+(?:\.\d+)?")


def _money_amounts(text: str) -> set[str]:
    return {_normalize_whitespace(match) for match in _MONEY_PATTERN.findall(text)}


def _normalize_whitespace(amount: str) -> str:
    return re.sub(r"\s+", " ", amount).strip()


def test_every_expected_answer_monetary_amount_appears_verbatim_in_input_text():
    cases = load_corpus(REAL_CORPUS_DIR)
    non_blocked = [case for case in cases if case.oracle.expected_answer is not None]
    assert non_blocked, "expected at least one non-blocked corpus case to check"

    failures = []
    for case in non_blocked:
        answer_amounts = _money_amounts(case.oracle.expected_answer)
        if not answer_amounts:
            continue
        text_amounts = _money_amounts(case.input.text)
        missing = answer_amounts - text_amounts
        if missing:
            failures.append(f"{case.input.sample_id}: {sorted(missing)}")

    assert not failures, (
        "expected_answer cites monetary figures absent from input.text -- this "
        "means the utility oracle depends on a compensation band/policy/floor "
        f"not derivable from common B0-B4 input: {failures}"
    )


def test_money_amount_checker_detects_an_amount_absent_from_input_text():
    # Not a check on the real corpus: pins that the extraction/containment
    # helper actually rejects an answer citing a figure the input never
    # states, so the real-corpus check above means something.
    text = "Salary: R$ 9200.00\n"
    answer = "The response states that the salary (R$ 9200.00) falls within the R$ 5000-10000 band."

    missing = _money_amounts(answer) - _money_amounts(text)

    assert missing == {"R$ 5000"}
