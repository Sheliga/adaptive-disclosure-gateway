"""The HR pilot's deterministic task analyzer (T07 / issue #6).

Implements ``base.TaskAnalyzer`` over hand-authored, controlled task
profiles: fixed indicator-term tables per category, plus explicit negation
detection. This is deliberately not a general-purpose NLP component -- see
the class docstring below for the exact forms recognized and the documented
limitations of that choice.

This module must never import ``adaptive_disclosure_gateway.corpus`` or
depend on ``sample_id``/``task_family``/any corpus file-naming convention
(pinned by ``tests/test_corpus_oracle_isolation.py``): the indicator tables
below are generic English terms authored for the pilot's task *style*, not
literal strings copied out of any one corpus case.
"""

from __future__ import annotations

import re
from collections.abc import Collection

from adaptive_disclosure_gateway.task_analysis.base import TaskAnalysis, TaskRelevance

# Indicator terms per category, matched as whole words/phrases against the
# task text only (never request.text, never a detected span's value). A
# category with no entry here has no controlled profile and always resolves
# NOT_RELEVANT -- see analyze()'s fallback branch.
CATEGORY_INDICATORS: dict[str, tuple[str, ...]] = {
    "employee_name": (
        "name",
        "identity",
        "identify",
        "identifying",
        "identified",
        "naming",
        "named",
    ),
    "cpf": ("cpf",),
    "cnpj": ("cnpj",),
    "email": ("email", "e-mail"),
    "phone": ("phone", "telephone"),
    "salary": ("salary", "compensation", "wage", "wages", "pay"),
    "department": ("department", "team", "division"),
    "medical_data": ("medical", "diagnosis", "health condition", "illness"),
}

# Phrases that, when present in a *non-negated* mention of a category, signal
# that a reduced/aggregated representation already serves the task -- so the
# exact original value is not needed. Only meaningful for a category whose
# generic action space (transformations/task_aware.py) has an intermediate
# step between REMOVE and PRESERVE (salary, for the pilot); for a category
# with no such step this signal has no effect on the resulting action, since
# "least revealing that still carries information" and "the exact value" then
# collapse to the same action anyway.
#
# Deliberately clause-scoped rather than indicator-token-scoped: if a single
# clause mentions two categories together with one of these words (e.g. "the
# average salary and department"), both are marked "without exact value"
# even though the distinction only changes the selected action for the
# numeric one. Documented limitation, not a hidden defect.
REDUCED_FORM_INDICATORS: tuple[str, ...] = (
    "average",
    "aggregate",
    "distribution",
    "estimate",
    "range",
)

# --- Negation ----------------------------------------------------------
#
# Two recognized negation shapes, because the same cue word can put the
# negated subject on either side of it depending on English sentence
# structure, and treating both identically breaks one direction or the
# other:
#
# WHOLE-SENTENCE cues ("Salary and CPF are not needed for this summary.",
# "Salary and CPF must not be included.") typically state the subject
# *before* the cue. The whole sentence containing the cue is treated as
# negated.
#
# PREFIX cues ("without disclosing their identity or department.", "Do not
# include salary or CPF.") typically introduce a clause whose object
# *follows* the cue. Only the text from the cue to the end of that sentence
# is treated as negated; text before the cue in the same sentence (often the
# task's main instruction) is left positive. This distinction is what keeps
# "Estimate the average salary band ..., without identifying any individual
# employee." from having "without" wipe out "salary" -- a naive
# whole-sentence rule would get this one backwards.
_WHOLE_SENTENCE_NEGATION_CUES: tuple[str, ...] = (
    "not needed",
    "not required",
    "not necessary",
    "must not",
    "should not",
    "cannot",
    "can not",
)
_PREFIX_NEGATION_CUES: tuple[str, ...] = (
    "without",
    "do not",
    "does not",
    "don't",
    "doesn't",
    "avoid",
    "refrain from",
)

_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")
_WHOLE_SENTENCE_PATTERN = re.compile(
    "|".join(re.escape(cue) for cue in _WHOLE_SENTENCE_NEGATION_CUES), re.IGNORECASE
)
_PREFIX_PATTERN = re.compile(
    "|".join(re.escape(cue) for cue in _PREFIX_NEGATION_CUES), re.IGNORECASE
)


def _split_positive_and_negated(task: str) -> tuple[str, str]:
    """Split ``task`` into its non-negated and negated text, sentence by
    sentence. See the module-level comment above for the two negation
    shapes this distinguishes.
    """
    positive_parts: list[str] = []
    negated_parts: list[str] = []
    for sentence in _SENTENCE_SPLIT_PATTERN.split(task.strip()):
        if not sentence:
            continue
        if _WHOLE_SENTENCE_PATTERN.search(sentence):
            negated_parts.append(sentence)
            continue
        prefix_match = _PREFIX_PATTERN.search(sentence)
        if prefix_match:
            positive_parts.append(sentence[: prefix_match.start()])
            negated_parts.append(sentence[prefix_match.start() :])
            continue
        positive_parts.append(sentence)
    return " ".join(positive_parts), " ".join(negated_parts)


def _contains(term: str, text: str) -> bool:
    return re.search(rf"\b{re.escape(term)}\b", text, re.IGNORECASE) is not None


class DeterministicTaskAnalyzer:
    """The pilot's deterministic ``TaskAnalyzer`` (T07 / issue #6).

    ``analyze`` receives *only* ``task`` and ``categories`` -- the structural
    guarantee documented on ``base.TaskAnalyzer`` -- and is a pure function
    of those two arguments: the same task text and category set always
    produce the same relevance judgement, with no randomness, external
    state, or corpus/oracle lookup of any kind.

    Determination per category:

    1. Split ``task`` into non-negated and negated text (see
       ``_split_positive_and_negated``).
    2. If none of the category's indicator terms appear anywhere ->
       ``NOT_RELEVANT`` (the task never mentions it).
    3. If an indicator term appears only in the negated text ->
       ``NOT_RELEVANT`` (explicit negation).
    4. If an indicator term appears only in the non-negated text -> relevant;
       ``RELEVANT_WITHOUT_EXACT_VALUE`` if a reduced-form indicator also
       appears in the non-negated text, otherwise
       ``RELEVANT_WITH_EXACT_VALUE``.
    5. If an indicator term appears in *both* -> the signal is genuinely
       conflicting (e.g. the task both names and disclaims the same
       category in different sentences) -> ``AMBIGUOUS`` rather than
       guessing which mention wins.

    Known limitations (documented, not hidden):

    - clause boundaries are ASCII sentence punctuation only; a negation
      spanning an independent clause joined without a sentence terminator
      (e.g. two clauses joined only by "and", no comma or period) is not
      recognized;
    - double negation ("not unnecessary") is read as a single negation;
    - the reduced-vs-exact heuristic only recognizes the configured cue
      words (``REDUCED_FORM_INDICATORS``); a task that needs an approximate
      figure but is phrased without any of them is read as needing the
      exact value;
    - the indicator/negation tables are hand-authored for the HR pilot's
      controlled task profiles (docs/experimental-design.md), not a
      general-purpose negation-scope resolver -- a task phrased very
      differently from the pilot's style may be misclassified. Any such
      misclassification found against the frozen HR corpus is a documented
      B3 behavior/limitation to report, never a reason to special-case
      corpus content in this analyzer (CLAUDE.md's corpus-freeze rule).
    """

    def analyze(self, task: str, categories: Collection[str]) -> TaskAnalysis:
        positive_text, negated_text = _split_positive_and_negated(task)
        relevance: dict[str, TaskRelevance] = {}

        for category in categories:
            indicators = CATEGORY_INDICATORS.get(category)
            if not indicators:
                relevance[category] = TaskRelevance.NOT_RELEVANT
                continue

            found_positive = any(_contains(term, positive_text) for term in indicators)
            found_negated = any(_contains(term, negated_text) for term in indicators)

            if found_positive and found_negated:
                relevance[category] = TaskRelevance.AMBIGUOUS
            elif found_positive:
                found_reduced = any(
                    _contains(term, positive_text) for term in REDUCED_FORM_INDICATORS
                )
                relevance[category] = (
                    TaskRelevance.RELEVANT_WITHOUT_EXACT_VALUE
                    if found_reduced
                    else TaskRelevance.RELEVANT_WITH_EXACT_VALUE
                )
            else:
                relevance[category] = TaskRelevance.NOT_RELEVANT

        return TaskAnalysis(relevance_by_category=relevance)
