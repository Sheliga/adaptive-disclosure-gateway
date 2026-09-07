"""Development/reporting tool: B3 -- Task-aware vs. the frozen HR corpus's
ground truth (T07 / issue #6, PR #33 review round).

This intentionally replaces a former pytest suite invariant
(``tests/test_task_aware.py::test_b3_decisions_stay_within_the_frozen_corpus_oracles_acceptable_actions``)
that required every one of the 13 frozen ``corpus/hr/v1`` cases' B3
decisions to fall inside that case's oracle-acceptable action set. Once
``task_analysis/deterministic.py`` defaults an ambiguous/under-evidenced
positive category mention to ``RELEVANT_WITHOUT_EXACT_VALUE`` rather than
escalating to ``RELEVANT_WITH_EXACT_VALUE`` by default (the safer,
default-to-least-revealing direction CLAUDE.md and this review round
require), 100% conformance against one specific frozen corpus is no longer
a property the analyzer is entitled to have, and asserting it in the test
suite would turn the corpus into a de facto specification the analyzer is
tuned to match -- exactly what the corpus-freeze rule and issue #6 forbid.

So this script *reports* convergence/divergence instead of gating a build
on it. It is deliberately not a pytest test: a check that can never fail a
build is not a test (CLAUDE.md's "no sanity tests" rule cuts the other way
too -- a test that is *expected* to sometimes fail by design is not a test
either, it is a measurement). Divergence found here is B3 experimental
behavior to carry into T10's utility/conformance scoring, not a defect to
patch by widening the analyzer's indicator tables against this one corpus.

The oracle is read here only to report against -- never passed to
``TaskAwareDiscloser`` or to ``CorpusCaseInput.to_disclosure_request()``.
``tests/test_corpus_oracle_isolation.py`` pins by AST inspection that no
production module has any import path to it at all; this script lives
outside ``src/`` and is not production code, so that isolation is
unaffected by this script importing ``adaptive_disclosure_gateway.corpus``.

Usage::

    python scripts/report_b3_corpus_divergence.py
"""

from __future__ import annotations

from pathlib import Path

from adaptive_disclosure_gateway.corpus.loader import load_corpus
from adaptive_disclosure_gateway.detection import Detector
from adaptive_disclosure_gateway.domain import DisclosureRequest
from adaptive_disclosure_gateway.policies import PolicyRepository
from adaptive_disclosure_gateway.transformations import TaskAwareDiscloser
from adaptive_disclosure_gateway.vault import InMemoryVault

REPO_ROOT = Path(__file__).parents[1]
POLICY_DIR = REPO_ROOT / "configs" / "policies"
CORPUS_DIR = REPO_ROOT / "corpus" / "hr" / "v1" / "cases"

# A fixed harness session id, filled in only for a case that omits one in
# its own YAML -- exactly what a real caller supplying the SESSION-scope
# lifecycle identifier would do (see pipeline.py's "identifier contract"
# docstring). Never overrides a case that already supplies its own.
_HARNESS_SESSION_ID = "corpus-harness-session"


def _request_for(case_input) -> DisclosureRequest:
    request = case_input.to_disclosure_request()
    if request.context.session_id is None:
        context = request.context.model_copy(update={"session_id": _HARNESS_SESSION_ID})
        return DisclosureRequest(text=request.text, task=request.task, context=context)
    return request


def main() -> None:
    discloser = TaskAwareDiscloser(
        vault=InMemoryVault(), policy_repository=PolicyRepository.from_directory(POLICY_DIR)
    )
    cases = load_corpus(CORPUS_DIR)
    if not cases:
        print(f"no corpus cases found under {CORPUS_DIR}")
        return

    total_spans = 0
    divergent_spans = 0
    rows: list[str] = []

    for case in cases:
        sample_id = case.input.sample_id

        if case.oracle.expected_block_request:
            rows.append(f"{sample_id}: SKIPPED (oracle expects BLOCK_REQUEST for the whole case)")
            continue

        request = _request_for(case.input)
        spans = Detector().detect(request.text)
        result = discloser.sanitize(request, spans)

        if result.status != "allowed":
            rows.append(
                f"{sample_id}: DIVERGENCE  case=* got_status={result.status!r} "
                "(oracle expected an allowed result)"
            )
            continue

        actions_by_category = {}
        for decision in result.decisions:
            actions_by_category.setdefault(decision.category, decision.action)

        for span in case.oracle.expected_spans:
            total_spans += 1
            got = actions_by_category.get(span.category)
            got_value = got.value if got is not None else None
            acceptable = sorted(action.value for action in span.expected_actions)
            converged = got_value in acceptable
            if not converged:
                divergent_spans += 1
            marker = "CONVERGED " if converged else "DIVERGENCE"
            rows.append(
                f"{sample_id}/{span.category}: {marker}  got={got_value!r} acceptable={acceptable}"
            )

    print("B3 vs. corpus/hr/v1 (13-case frozen HR pilot corpus) -- development report only")
    print("=" * 78)
    for row in rows:
        print(row)
    print("-" * 78)
    print(f"{total_spans - divergent_spans}/{total_spans} spans converged with the oracle")
    if divergent_spans:
        print(
            f"{divergent_spans} divergence(s) found -- documented B3 experimental behavior, "
            "not a defect to fix by tuning the analyzer against this corpus "
            "(see this script's module docstring)."
        )


if __name__ == "__main__":
    main()
