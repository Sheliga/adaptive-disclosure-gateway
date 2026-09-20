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

Indicator-table safety rule (PR #33 review round): a false NEGATIVE here
(the analyzer misses a genuine mention) only costs utility -- the caller
falls back to that category's least-disclosing action, same as any other
NOT_RELEVANT outcome. A false POSITIVE is strictly worse -- a bare,
ambiguous indicator term (e.g. a former version of this table used the
single word "pay", which also matches ordinary verbs like "pay attention")
can make a category look relevant to a task that never asked for it,
driving the resolved action all the way up to PRESERVE and *increasing*
disclosure beyond what the task required. So every indicator below is
chosen to be unambiguous on its own, using a multi-word phrase where a
single word would collide with common English usage unrelated to the
category. When a term's own meaning is genuinely ambiguous and no
unambiguous phrase covers the same need, the term is simply left out --
the resulting NOT_RELEVANT is not a silent fallback to PRESERVE, it is the
same explicit "least disclosing action in the category's action space"
outcome NOT_RELEVANT always produces (see transformations/task_aware.py's
``_select_action``). See tests/test_task_analysis_deterministic.py's and
tests/test_task_aware.py's negative-control tests for concrete examples
this rule rules out, and their paired positive controls proving the
hardening does not blind the analyzer to genuine mentions.

The same asymmetry governs the exact-value-vs-reduced-form choice below
(``EXACT_VALUE_INDICATORS``): a positive mention with no explicit, narrow
evidence that the *exact* value is needed resolves to
``RELEVANT_WITHOUT_EXACT_VALUE``, never to ``RELEVANT_WITH_EXACT_VALUE`` by
default. Absence of signal must never escalate to the more revealing
representation. Concretely: a false positive that increases disclosure
(marking a category relevant, or "needs the exact value", when the task
never asked for that) is more serious than a false negative/conservative
read (marking it not relevant, or "does not need the exact value", when it
actually did) -- the former exposes data the task did not require, while
the latter only costs utility. That utility cost is a B3 result to be
*measured* against the frozen HR corpus in T10, not a defect to eliminate
here: this analyzer's indicator tables are never tuned retrospectively
against the corpus's expected actions to make a specific case converge
(CLAUDE.md's corpus-freeze rule) -- see ``scripts/report_b3_corpus_divergence.py``
for the current, expected divergence this produces against
``corpus/hr/v1``.

Exact-value evidence must also be bound to the category it actually
modifies (PR #33 second review round): an earlier version of this module
searched ``EXACT_VALUE_INDICATORS`` across the task's *entire* positive
text, so an exactness cue that plainly belonged to one category's mention
(e.g. "the exact CPF") also escalated any other, unrelated category
mentioned anywhere else in the task (e.g. "salary" in a later sentence) to
``RELEVANT_WITH_EXACT_VALUE`` -- a false positive strictly worse than the
false negatives this docstring already discusses, because it silently
increases disclosure for a category the task never asked to have exactly.
That round scoped the simple-cue mechanism to a single clause
(``_split_into_clauses``), but within that clause still bound the cue to
*every* category the clause positively mentioned -- literally the same
"distribute the cue to every present category" behavior, just with a
smaller blast radius. Trivial rewordings that keep two categories in one
clause instead of splitting them across sentences (joined by "and", by a
comma, or by "then") reproduced the identical leak: "Use the exact employee
name and summarize the salary band." still escalated "salary" to
``RELEVANT_WITH_EXACT_VALUE`` even though the cue plainly modifies
"employee name". A third review round replaced whole-clause binding with
nearest-mention binding: within a clause, a cue binds only the category
mention closest to it in token distance, and only when that distance is
within a small, fixed window and unambiguous (no tie with another
category's mention at the same distance) -- see
``_nearest_bound_categories`` below for the exact rule, its window and the
tie-break, and its documented limitations.

An earlier version of this docstring justified the whole-clause mechanism's
residual imprecision as "inert" against the pilot's action spaces, reasoning
that only ``salary`` has a third action tier
(``transformations/task_aware.py``'s ``TASK_AWARE_ACTION_SPACES``) where
``RELEVANT_WITH_EXACT_VALUE`` and ``RELEVANT_WITHOUT_EXACT_VALUE`` resolve
to *different* actions. That reasoning had the direction backwards: it is
exactly *because* ``salary`` is the one category whose action actually
changes with this bit that a cue belonging to some other category
incidentally binding ``salary`` too is not inert -- it is the defect. The
"inert" framing was only ever true for the mirror direction (a cue
genuinely bound to ``salary`` incidentally also binding a two-tier category
like ``department`` alongside it, which cannot change that category's
resolved action either way); it never covered a two-tier category's cue
leaking into ``salary``.
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
        "identity",
        "identify",
        "identifying",
        "identified",
        "named",
        "employee name",
        "employee's name",
        "by name",
        "full name",
        "person's name",
        "name of the employee",
    ),
    "cpf": ("cpf",),
    "cnpj": ("cnpj",),
    "email": ("email", "e-mail"),
    "phone": ("phone", "telephone"),
    "salary": (
        "salary",
        "compensation",
        "wage",
        "wages",
        "remuneration",
        "pay band",
        "pay range",
        "pay grade",
        "pay rate",
        "payroll",
        "paycheck",
        "take-home pay",
    ),
    "department": (
        "department",
        "which team",
        "what team",
        "their team",
        "employee's team",
        "which division",
        "employee's division",
    ),
    "medical_data": ("medical", "diagnosis", "health condition", "illness"),
    # --- Contracts domain (Issue #56), authored under exactly the same
    # false-positive-is-worse-than-false-negative rule as the HR tables
    # above. Ambiguous single words that collide with ordinary English are
    # left out rather than included and hoped for: bare "party" (a social
    # event), bare "value"/"amount" (any quantity at all), bare "fine" ("that
    # is fine"), and bare "term" ("long term") are all absent for that
    # reason; the multi-word phrasings below cover the same intent without
    # matching those idioms. None of these were chosen against any Contracts
    # case -- no Contracts corpus exists yet (T24 / Issue #37).
    "party_name": (
        "contracting party",
        "contracting parties",
        "contracted party",
        "contracted parties",
        "counterparty",
        "counterparties",
        "party name",
        "names of the parties",
        "which companies",
        "which organizations",
    ),
    "representative_name": (
        "legal representative",
        "legal representatives",
        "representative name",
        "signatory",
        "signatories",
        "who signed",
    ),
    "bank_account": (
        "bank account",
        "banking details",
        "account number",
        "payment account",
    ),
    "contract_value": (
        "contract value",
        "contract amount",
        "contract price",
        "total value",
        "financial terms",
        "monetary value",
    ),
    "penalty_amount": (
        "penalty",
        "penalties",
        "penalty amount",
        "penalty clause",
        "late fee",
        "late fees",
        "liquidated damages",
    ),
    "deadline": (
        "deadline",
        "deadlines",
        "due date",
        "due dates",
        "delivery date",
        "payment date",
        "expiry date",
        "expiration date",
        "term of the contract",
    ),
}
# Bare "name"/"naming" and bare "pay"/"team"/"division" were removed from the
# tables above (PR #33 review round): each collided with common English
# usage unrelated to the category ("Pay attention...", "team player", "long
# division", "the department name") and would falsely mark the category
# relevant -- see the module docstring's safety rule. The multi-word phrases
# above cover the pilot's genuine task style (including the frozen corpus's
# "addressed by name" and "this employee's team" phrasings) without matching
# those idioms.

# Phrases whose presence in a *non-negated* mention of a category is narrow,
# explicit evidence that the *exact* original value (not a reduced/aggregated
# representation) is needed. Only meaningful for a category whose generic
# action space (transformations/task_aware.py) has an intermediate step
# between REMOVE and PRESERVE (salary, for the pilot); for a category with no
# such step, "the least revealing representation that still carries
# information" and "the exact value" collapse to the same action regardless
# of this signal.
#
# Deliberately narrow, for the same false-positive-is-worse-than-false-
# negative reason as CATEGORY_INDICATORS above: a positive category mention
# with no evidence here already resolves to RELEVANT_WITHOUT_EXACT_VALUE (see
# analyze() below) -- these terms only ever *upgrade* that default to
# RELEVANT_WITH_EXACT_VALUE, so a term here that turns out ambiguous would be
# the direction of defect this whole review round exists to close. None of
# these were chosen to make any specific frozen-corpus case converge; a task
# that needs the exact value but is phrased without one of them is read as
# not needing it, which is a documented utility cost, not a bug to patch by
# widening this list against the corpus.
EXACT_VALUE_INDICATORS: tuple[str, ...] = (
    "exact",
    "exactly",
    "precise",
    "precisely",
    "verbatim",
    "specific figure",
    "individual value",
)

# Two-sided "wrapper" cues: a prefix word and a suffix word that, together,
# express exactness by SURROUNDING a category's own indicator mention --
# needed for phrasings like "specific salary figure", where the category
# term sits grammatically *inside* the exactness expression ("specific ...
# figure") rather than next to a single contiguous cue phrase from
# EXACT_VALUE_INDICATORS above. Recognized only within one clause (see
# _split_into_clauses below), with the prefix strictly before the suffix
# and no more than _WRAPPER_MAX_SPAN tokens between them -- kept small and
# fixed so this stays a narrow, local pattern, not a search over the whole
# task text. See _wrapper_bound_categories's docstring for what happens
# when a wrapper occurrence encloses more than one category's mention.
_EXACT_VALUE_WRAPPERS: tuple[tuple[str, str], ...] = (("specific", "figure"),)
_WRAPPER_MAX_SPAN = 4

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


def _split_into_clauses(task: str) -> list[tuple[str, bool]]:
    """Split ``task`` into ``(fragment, is_positive)`` clauses, sentence by
    sentence. See the module-level comment above for the two negation
    shapes this distinguishes.

    This is also the binding unit ``_exact_value_bound_categories`` below
    uses: an exactness cue and a category mention only bind each other when
    they fall in the same element of this list -- however close together
    they may be on the page, two different elements (e.g. two different
    sentences) never bind.
    """
    clauses: list[tuple[str, bool]] = []
    for sentence in _SENTENCE_SPLIT_PATTERN.split(task.strip()):
        if not sentence:
            continue
        if _WHOLE_SENTENCE_PATTERN.search(sentence):
            clauses.append((sentence, False))
            continue
        prefix_match = _PREFIX_PATTERN.search(sentence)
        if prefix_match:
            clauses.append((sentence[: prefix_match.start()], True))
            clauses.append((sentence[prefix_match.start() :], False))
            continue
        clauses.append((sentence, True))
    return clauses


def _split_positive_and_negated(task: str) -> tuple[str, str]:
    """Split ``task`` into its non-negated and negated text. See
    ``_split_into_clauses`` for the underlying per-clause split this
    concatenates.
    """
    clauses = _split_into_clauses(task)
    positive_parts = [text for text, is_positive in clauses if is_positive]
    negated_parts = [text for text, is_positive in clauses if not is_positive]
    return " ".join(positive_parts), " ".join(negated_parts)


def _contains(term: str, text: str) -> bool:
    return re.search(rf"\b{re.escape(term)}\b", text, re.IGNORECASE) is not None


_WORD_PATTERN = re.compile(r"[a-z']+")


def _tokenize(text: str) -> list[str]:
    return _WORD_PATTERN.findall(text.lower())


def _phrase_positions(tokens: list[str], phrase: str) -> list[tuple[int, int]]:
    """Every inclusive ``(start, end)`` token-index span where ``phrase``'s
    own words appear contiguously in ``tokens``.
    """
    words = phrase.split()
    span = len(words)
    return [
        (i, i + span - 1) for i in range(len(tokens) - span + 1) if tokens[i : i + span] == words
    ]


def _wrapper_bound_categories(clause: str, categories: Collection[str]) -> set[str]:
    """Categories whose own indicator mention in ``clause`` is enclosed by
    one of ``_EXACT_VALUE_WRAPPERS`` (e.g. "specific salary figure" encloses
    "salary" between "specific" and "figure").

    If a single wrapper occurrence encloses more than one category's
    mention (e.g. "specific salary and CPF figure" encloses both "salary"
    and "cpf"), it is genuinely ambiguous which one the wrapper's exactness
    applies to -- there is only one "figure" being asked for and no
    deterministic way to tell which co-mentioned category it refers to.
    Per this module's default-to-least-revealing rule, that occurrence
    binds neither category, rather than guessing or binding both.
    """
    tokens = _tokenize(clause)
    bound: set[str] = set()
    for prefix, suffix in _EXACT_VALUE_WRAPPERS:
        prefix_positions = [i for i, token in enumerate(tokens) if token == prefix]
        suffix_positions = [i for i, token in enumerate(tokens) if token == suffix]
        for p in prefix_positions:
            candidate_suffixes = [s for s in suffix_positions if p < s <= p + _WRAPPER_MAX_SPAN]
            if not candidate_suffixes:
                continue
            s = min(candidate_suffixes)
            enclosed = {
                category
                for category, indicators in CATEGORY_INDICATORS.items()
                if category in categories
                for term in indicators
                for start, end in _phrase_positions(tokens, term)
                if p < start and end < s
            }
            if len(enclosed) == 1:
                bound |= enclosed
            # len(enclosed) > 1: ambiguous via this wrapper occurrence --
            # deliberately bound to neither category, not a guess.
    return bound


# Maximum token distance (tokens strictly between a cue occurrence and a
# category mention, in the same clause) at which the simple-cue mechanism in
# ``_nearest_bound_categories`` will still bind them. Calibrated against
# this module's own positive controls, all of which need a window no wider
# than this to bind (an adjacent cue and category term is distance 0; "the
# salary value precisely" -- one word, "value", between them -- is distance
# 1); the mandatory negative controls never need the window at all, because
# in every one of them the unrelated category the old whole-clause mechanism
# incorrectly bound sits several tokens further from the cue than the
# category actually being addressed, so nearest-mention binding already
# picks the right one regardless of how wide this window is. Kept small and
# fixed, like ``_WRAPPER_MAX_SPAN`` above, so this stays a narrow, local
# pattern rather than a search over the whole clause.
_EXACT_VALUE_WINDOW = 3


def _token_distance(cue_span: tuple[int, int], term_span: tuple[int, int]) -> int:
    """Number of tokens strictly between two non-overlapping, inclusive
    ``(start, end)`` token-index spans -- 0 when they are adjacent.
    """
    cue_start, cue_end = cue_span
    term_start, term_end = term_span
    if term_end < cue_start:
        return cue_start - term_end - 1
    return term_start - cue_end - 1


def _nearest_bound_categories(clause: str, categories: Collection[str]) -> set[str]:
    """Categories whose own indicator mention in ``clause`` is the single
    nearest one, in token distance, to an ``EXACT_VALUE_INDICATORS`` cue
    occurrence in that same clause -- and only when that distance is within
    ``_EXACT_VALUE_WINDOW``.

    This is the simple-cue binding mechanism, replacing the "a cue anywhere
    in the clause binds every category the clause mentions" rule the third
    review round closed (see the module docstring). Per cue occurrence:

    - compute the token distance (``_token_distance``) from the cue to the
      nearest mention of each category present in ``categories`` and
      mentioned in this clause;
    - if exactly one category achieves the minimum distance, and that
      distance is at most ``_EXACT_VALUE_WINDOW``, the cue binds that
      category, and only that one;
    - if two or more categories tie for the minimum distance, or the
      minimum exceeds the window, the cue binds nothing. Per this module's
      default-to-least-revealing rule, an unresolvable or too-distant cue
      must never guess -- see ``test_task_analysis_deterministic.py``'s
      dedicated tie-break test for a constructed case where a cue sits
      exactly equidistant between two categories.

    Deliberately not a syntactic/grammatical attribution (no parsing of
    which noun phrase a cue's adjective or adverb actually modifies) --
    this module stays a fixed, token-distance heuristic, not a
    general-purpose NLP component. A cue whose true grammatical target is
    farther, in raw token count, from the cue than an unrelated category's
    incidental mention (e.g. a category name embedded inside a compound
    noun the cue does not actually describe) will not bind its true target;
    this is a documented, accepted utility cost of the same kind as this
    module's other heuristics, not a defect to chase with deeper parsing.
    """
    tokens = _tokenize(clause)
    cue_spans = [span for cue in EXACT_VALUE_INDICATORS for span in _phrase_positions(tokens, cue)]
    if not cue_spans:
        return set()

    category_spans: dict[str, list[tuple[int, int]]] = {}
    for category in categories:
        indicators = CATEGORY_INDICATORS.get(category)
        if not indicators:
            continue
        spans = [span for term in indicators for span in _phrase_positions(tokens, term)]
        if spans:
            category_spans[category] = spans

    bound: set[str] = set()
    for cue_span in cue_spans:
        distances = {
            category: min(_token_distance(cue_span, span) for span in spans)
            for category, spans in category_spans.items()
        }
        if not distances:
            continue
        nearest_distance = min(distances.values())
        if nearest_distance > _EXACT_VALUE_WINDOW:
            continue
        nearest_categories = [
            category for category, distance in distances.items() if distance == nearest_distance
        ]
        if len(nearest_categories) == 1:
            bound.add(nearest_categories[0])
        # len(nearest_categories) > 1: a genuine tie -- deliberately bound
        # to neither category, not a guess.
    return bound


def _exact_value_bound_categories(task: str, categories: Collection[str]) -> set[str]:
    """Categories for which ``task``'s positive text carries narrow,
    explicit evidence, deterministically scoped to a single clause (see
    ``_split_into_clauses``), that the exact original value is needed.

    Two clause-local binding mechanisms:

    - simple cue: see ``_nearest_bound_categories`` above -- an
      ``EXACT_VALUE_INDICATORS`` term binds only the nearest category
      mention in the same clause, within a small token window, and only
      when that nearest mention is unambiguous (no tie);
    - wrapper cue: see ``_wrapper_bound_categories`` above, for phrasings
      where the category term sits grammatically inside the exactness
      expression itself (e.g. "specific salary figure").

    Operates on positive clauses only -- the existing negated/positive
    split (``_split_into_clauses``) runs first and is unchanged; a clause
    this function never sees never contributes exact-value evidence,
    exactly as before.
    """
    bound: set[str] = set()
    for clause, is_positive in _split_into_clauses(task):
        if not is_positive:
            continue
        bound |= _nearest_bound_categories(clause, categories)
        bound |= _wrapper_bound_categories(clause, categories)
    return bound


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
       ``RELEVANT_WITH_EXACT_VALUE`` only if that category is one of
       ``_exact_value_bound_categories(task, categories)`` -- narrow,
       explicit evidence, bound to *this* category specifically within a
       single clause, that the exact value (not a reduced representation)
       is needed; otherwise ``RELEVANT_WITHOUT_EXACT_VALUE``. This is a
       default-to-least-revealing rule (PR #33 review round): absence of
       evidence for the exact value never escalates to it, and evidence
       bound to a *different* category never escalates this one either
       (PR #33 second review round -- see ``_exact_value_bound_categories``'s
       docstring for the binding rule and its documented limitations).
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
    - the exact-value heuristic only recognizes the configured cue words
      (``EXACT_VALUE_INDICATORS``); a task that genuinely needs the exact
      value but is phrased without any of them is read as needing only a
      reduced representation. This is a deliberate, documented utility cost
      (see the module docstring's safety rule), not a defect to close by
      widening the cue list -- especially not to make any one frozen-corpus
      case converge;
    - the indicator/negation tables are hand-authored for the HR pilot's
      controlled task profiles (docs/experimental-design.md), not a
      general-purpose negation-scope resolver -- a task phrased very
      differently from the pilot's style may be misclassified. Any such
      misclassification found against the frozen HR corpus is a documented
      B3 behavior/limitation to report (see
      ``scripts/report_b3_corpus_divergence.py``), never a reason to
      special-case corpus content in this analyzer (CLAUDE.md's
      corpus-freeze rule).
    """

    def analyze(self, task: str, categories: Collection[str]) -> TaskAnalysis:
        positive_text, negated_text = _split_positive_and_negated(task)
        exact_bound_categories = _exact_value_bound_categories(task, categories)
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
                # Default to the least-revealing relevant level: only
                # narrow, explicit evidence *bound to this category*
                # (_exact_value_bound_categories) upgrades this to
                # RELEVANT_WITH_EXACT_VALUE. Absence of that evidence -- or
                # evidence bound to a different category instead -- never
                # escalates to the more revealing representation.
                found_exact = category in exact_bound_categories
                relevance[category] = (
                    TaskRelevance.RELEVANT_WITH_EXACT_VALUE
                    if found_exact
                    else TaskRelevance.RELEVANT_WITHOUT_EXACT_VALUE
                )
            else:
                relevance[category] = TaskRelevance.NOT_RELEVANT

        return TaskAnalysis(relevance_by_category=relevance)
