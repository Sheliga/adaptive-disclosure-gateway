"""B4 -- Policy-governed metadata extraction from its own OTel span (T10 /
issue #8).

``transformations/policy_governed.py`` already computes and records, as
plain span attributes on its own ``policy_governed.sanitize`` span, exactly
the metadata the B3->B4 comparison needs: the contextual matrix cell
identifier(s) that fired for this case, which categories were
policy-restricted, which were impossible-under-policy, and which block
reason classes (if any) applied. This module *reads that span back* rather
than recomputing any of it -- reusing the identifier B4 already produces
(CLAUDE.md-adjacent instruction from the T10 brief), never inventing a
second, parallel implementation that could drift from the production one.

No sensitive value ever reaches these attributes in the first place (see
``policy_governed.py``'s own docstring); this module only reshapes already
-safe span attributes into a typed dataclass.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from opentelemetry.sdk.trace import ReadableSpan

_B4_SPAN_NAME = "policy_governed.sanitize"


@dataclass(frozen=True)
class B4Metadata:
    matrix_cells: tuple[str, ...]
    policy_restricted_categories: tuple[str, ...]
    impossible_under_policy_categories: tuple[str, ...]
    block_reason_classes: tuple[str, ...]
    blocked: bool | None
    policy_version: str | None


def extract_b4_metadata(spans: Sequence[ReadableSpan]) -> B4Metadata | None:
    """Read B4's own ``policy_governed.sanitize`` span attributes back into a
    ``B4Metadata``, or ``None`` if no such span was recorded (this is not a
    B4 run).
    """
    span = next((s for s in spans if s.name == _B4_SPAN_NAME), None)
    if span is None:
        return None

    attributes = span.attributes or {}
    return B4Metadata(
        matrix_cells=tuple(attributes.get("policy_governed.matrix_cells", ())),
        policy_restricted_categories=tuple(
            attributes.get("policy_governed.policy_restricted_categories", ())
        ),
        impossible_under_policy_categories=tuple(
            attributes.get("policy_governed.impossible_under_policy_categories", ())
        ),
        block_reason_classes=tuple(attributes.get("policy_governed.block_reason_classes", ())),
        blocked=attributes.get("policy_governed.blocked"),
        policy_version=attributes.get("policy_governed.policy_version"),
    )
