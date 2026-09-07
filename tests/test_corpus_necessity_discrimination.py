"""Necessity-discrimination invariant for the frozen HR pilot corpus (T09 /
issue #4, Phase A -- PR #31 review round 3).

An audit of the corrected corpus (PR #31 review round 2) found that
``employee_name`` was labeled ``task_necessity: not_required`` in all 16 of
its occurrences and never once ``required``. That is a discrimination
defect, not merely a skew: a scoring strategy that constantly suppresses
employee identity, doing no task analysis whatsoever, satisfies the
``employee_name`` oracle perfectly across the whole corpus. A category that
is always ``NOT_REQUIRED`` cannot distinguish a treatment that genuinely
reasons about task-dependent necessity (B3 -- Task-aware) from one that
blindly suppresses that category on every input. Since v1 freezes on merge
(``corpus/hr/v1/README.md``), shipping this gap would make it permanent for
every pilot run scored against v1.

The invariant: every category annotated anywhere in the corpus, except an
explicit, documented exclusion set, must appear at least once as
``required`` and at least once as ``not_required``. Only ``cpf`` is
excluded. In the HR pilot domain modeled here, CPF is never necessary for
any of the four task families (salary analysis, team summaries, department
aggregation, medical/prohibited block all state or imply CPF is
dispensable) -- forcing a ``required`` CPF span into the corpus to satisfy
this test would itself be an artificial, unfalsifiable annotation, which is
exactly what ``tests/test_corpus_task_necessity_coherence.py`` and
``tests/test_corpus_answer_grounded_in_input.py`` exist to prevent for the
answer oracle. No other category is exempt.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from adaptive_disclosure_gateway.corpus import TaskNecessity, load_corpus

REPO_ROOT = Path(__file__).parents[1]
REAL_CORPUS_DIR = REPO_ROOT / "corpus" / "hr" / "v1" / "cases"

# The only category permitted to be always not_required. See module
# docstring for why: CPF is genuinely never task-necessary in this pilot's
# domain, so demanding a `required` CPF span would force an artificial case.
DISCRIMINATION_EXEMPT_CATEGORIES = frozenset({"cpf"})


def test_every_non_exempt_category_has_at_least_one_required_and_one_not_required_span():
    cases = load_corpus(REAL_CORPUS_DIR)
    assert cases, "expected at least one corpus case to check"

    required_counts: Counter[str] = Counter()
    not_required_counts: Counter[str] = Counter()
    categories_seen: set[str] = set()

    for case in cases:
        for span in case.oracle.expected_spans:
            categories_seen.add(span.category)
            if span.task_necessity is TaskNecessity.REQUIRED:
                required_counts[span.category] += 1
            else:
                not_required_counts[span.category] += 1

    non_exempt_categories = categories_seen - DISCRIMINATION_EXEMPT_CATEGORIES
    assert non_exempt_categories, "expected at least one non-exempt category to check"

    failures = []
    for category in sorted(non_exempt_categories):
        required = required_counts[category]
        not_required = not_required_counts[category]
        if required == 0 or not_required == 0:
            failures.append(f"{category}: required={required} not_required={not_required}")

    assert not failures, (
        "category never discriminates task_necessity across the corpus (a "
        "constant-suppression or constant-preserve strategy would satisfy "
        "it perfectly, so it cannot distinguish real task-awareness from "
        "blind action on this category): " + "; ".join(failures)
    )
