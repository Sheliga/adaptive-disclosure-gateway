"""Shared task-relevance -> action selection (T07 -- Task-aware / T08 --
Policy-governed, issue #7 review round).

``select_action_for_relevance`` is extracted, verbatim in behavior, from
what used to be ``transformations/task_aware.py``'s own module-private
``_select_action``. It is the single rule both B3 -- Task-aware and B4 --
Policy-governed use to pick the least-disclosing action inside an
already-ordered candidate action space that still satisfies a given
``TaskRelevance``:

    REMOVE < PSEUDONYMIZE < GENERALIZE < PRESERVE

B3 calls it with its own fixed, generic, per-category action space
(``task_aware.TASK_AWARE_ACTION_SPACES``, hand-authored already in this
order). B4 calls it with whatever action space
``PolicyRepository.decide()`` resolves for a ``TASK_DEPENDENT`` category --
after first passing it through ``order_action_space`` below, because a
policy YAML's ``allowed_actions``/``purpose_actions`` list is author-ordered
and not guaranteed to already follow this canonical ordering the way B3's
hand-authored spaces are. Neither caller may ever widen this function's
``action_space`` argument beyond what it was given -- this function only
ever returns a member of ``action_space``, never anything else, and its
policy-side caller decides how that space itself gets built (see
``transformations/policy_governed.py``, which is the only module allowed to
call ``PolicyRepository.decide()`` -- see ``tests/test_policy_governed_isolation.py``).

``TaskRelevance.AMBIGUOUS`` is deliberately not accepted here -- both
callers resolve it themselves, before reaching this function, to their own
space's least-disclosing action, recorded with their own treatment-specific
audit wording (see ``task_aware.py``'s and ``policy_governed.py``'s own
``decide()`` closures).
"""

from __future__ import annotations

from collections.abc import Collection

from adaptive_disclosure_gateway.domain import DisclosureAction
from adaptive_disclosure_gateway.task_analysis.base import TaskRelevance

# The four disclosure-level actions, in canonical least->most disclosing
# order. BLOCK_REQUEST and TASK_DEPENDENT are not disclosure levels at all --
# the former ends a request before any of these apply, the latter is only a
# policy-rule marker that gets resolved into one of these four (or another
# BLOCK_REQUEST) before this module is ever consulted -- so neither belongs
# in this ladder.
CANONICAL_DISCLOSURE_ORDER: tuple[DisclosureAction, ...] = (
    DisclosureAction.REMOVE,
    DisclosureAction.PSEUDONYMIZE,
    DisclosureAction.GENERALIZE,
    DisclosureAction.PRESERVE,
)


def order_action_space(actions: Collection[DisclosureAction]) -> tuple[DisclosureAction, ...]:
    """Sort/filter ``actions`` into ``CANONICAL_DISCLOSURE_ORDER``.

    Any action in ``actions`` that is not one of the four canonical
    disclosure-level actions (e.g. a policy YAML mistakenly listing
    ``block_request`` or ``task_dependent`` inside ``allowed_actions``) is
    silently dropped from the result -- this function only ever orders and
    filters, it never raises. A caller that needs to detect and fail closed
    on that shrinkage (``transformations/policy_governed.py`` does) must
    compare the result's length against ``len(set(actions))`` itself.
    Duplicate entries in ``actions`` collapse to one, since ``action_space``
    is conceptually a set of candidate actions, not a multiset.
    """
    return tuple(action for action in CANONICAL_DISCLOSURE_ORDER if action in actions)


def select_action_for_relevance(
    level: TaskRelevance, action_space: tuple[DisclosureAction, ...]
) -> DisclosureAction:
    """Pick the first action in ``action_space`` (already ordered
    least-to-most disclosing) that satisfies ``level``. Never returns an
    action outside ``action_space``.

    - NOT_RELEVANT: the least disclosing action in the space.
    - RELEVANT_WITHOUT_EXACT_VALUE: the least disclosing action that still
      carries usable information -- the first action that is not REMOVE
      (REMOVE carries none).
    - RELEVANT_WITH_EXACT_VALUE: PRESERVE if and only if PRESERVE is in the
      space; otherwise the most disclosing action available (never invents
      an action outside the space).

    ``TaskRelevance.AMBIGUOUS`` is not accepted -- see this module's own
    docstring for why each caller resolves it before reaching here.
    """
    if level is TaskRelevance.NOT_RELEVANT:
        return action_space[0]
    if level is TaskRelevance.RELEVANT_WITHOUT_EXACT_VALUE:
        for action in action_space:
            if action is not DisclosureAction.REMOVE:
                return action
        return action_space[0]
    if level is TaskRelevance.RELEVANT_WITH_EXACT_VALUE:
        if DisclosureAction.PRESERVE in action_space:
            return DisclosureAction.PRESERVE
        return action_space[-1]
    raise AssertionError(f"unreachable task relevance level: {level!r}")
