"""Behavioral pin for ``transformations.decision_application.replace_ordered``
(T26 / issue #67): the shared literal-substring replacement primitive
extracted from ``reconstruct``'s own loop so the new restore-handle surface
(``application/restore_handle.py``) reuses exactly one token-replacement
algorithm instead of a second, independently written one.

The real defect this pins: replacing tokens in caller-supplied order instead
of longest-first can corrupt output when one token is a substring of
another (e.g. a collision-disambiguated pseudonym ``PSEUDO-x-1`` being a
prefix of ``PSEUDO-x-12``-shaped input) -- see
``vault/in_memory.py``'s own collision-suffix comment for why that shape is
reachable in production.
"""

from __future__ import annotations

from adaptive_disclosure_gateway.transformations.decision_application import replace_ordered


def test_replace_ordered_applies_every_pair():
    text = "Hello TOKEN_A, meet TOKEN_B."
    result = replace_ordered(text, [("TOKEN_A", "Alice"), ("TOKEN_B", "Bob")])
    assert result == "Hello Alice, meet Bob."


def test_replace_ordered_is_a_no_op_for_a_token_not_present():
    text = "Nothing to replace here."
    result = replace_ordered(text, [("TOKEN_A", "Alice")])
    assert result == text


def test_replace_ordered_requires_the_caller_to_have_sorted_longest_first():
    # A short token that is a prefix of a longer one, replaced FIRST (i.e.
    # the caller got the ordering wrong), corrupts the longer occurrence --
    # this test pins that replace_ordered itself does no reordering of its
    # own; callers (reconstruct, restore_pseudonyms) are responsible for
    # sorting longest-first before calling it.
    text = "See PSEUDO-x-1 and PSEUDO-x-12 in the text."
    wrong_order = replace_ordered(text, [("PSEUDO-x-1", "SHORT"), ("PSEUDO-x-12", "LONG")])
    assert wrong_order == "See SHORT and SHORT2 in the text."

    right_order = replace_ordered(text, [("PSEUDO-x-12", "LONG"), ("PSEUDO-x-1", "SHORT")])
    assert right_order == "See SHORT and LONG in the text."
