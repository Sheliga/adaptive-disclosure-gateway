"""Content-source selection for ``DisclosureApplicationService.build_application_request``
(T20 / issue #28, slice 2).

The guided UI can start a disclosure request from exactly one of three
places: pasted/typed text, an uploaded ``.txt``/``.md`` file, or a prepared
example. Deciding *which* source was actually supplied, resolving the task
(falling back to an example's own task only when the caller supplied none),
and layering an example's own governance fields under any explicit caller
override is application logic, not routing -- an HTTP route must stay a
thin parse-map-call-map shell (CLAUDE.md's "no domain logic in the HTTP
layer" rule), so none of this may live in ``api/``.

This is a small, separate module rather than inline code in ``service.py``
because it is pure (no I/O, no core call, no oracle) and independently
testable without constructing a whole ``DisclosureApplicationService`` --
only ``apply_example_governance_defaults`` needs an already-loaded
``CorpusCaseInput``, which ``DisclosureApplicationService.build_application_request``
supplies via its own ``load_example``.

No-leak invariant (CLAUDE.md): both exceptions below name only which
sources were supplied (by their parameter name -- "text", "file",
"example_id") or that a task is missing -- never any submitted content.
"""

from __future__ import annotations

import dataclasses

from adaptive_disclosure_gateway.application.contracts import GovernanceOverrides
from adaptive_disclosure_gateway.corpus.case_input import CorpusCaseInput


class ContentSourceError(Exception):
    """Raised when ``build_application_request`` was supplied zero, or more
    than one, of its three content sources (``text``, ``filename``+
    ``file_bytes``, ``example_id``) -- or an incomplete file source
    (exactly one of ``filename``/``file_bytes``). Messages name only which
    source *slots* were supplied, never any content.
    """


class MissingTaskError(Exception):
    """Raised when ``build_application_request`` has no task to work with:
    the caller supplied no ``task`` and the content source is not an
    example (whose own task could otherwise stand in).
    """


# The GovernanceContext fields an example may supply as defaults, in the
# order GovernanceOverrides declares them.
#
# Deliberately excludes requester_id/session_id/document_id/request_id:
# those identify a real requester/session/document lifecycle, which belongs
# to the caller/deployer configuration, never to a shared, reusable demo
# example.
#
# Deliberately excludes provider_class too, for a different reason. A
# prepared example describes a *scenario* -- which domain, purpose, policy
# version and requester role a request happens under. Which class of
# provider the request may actually egress to is a *deployment* fact, owned
# by whoever configured this service's ``Provider``. Letting an example
# override it broke the guided flow outright: every corpus case names
# ``external_llm``, so an example-sourced request run against a demo
# provider declaring anything else was allowed by the treatment and then
# correctly rejected at the provider boundary with
# ``ProviderClassMismatchError`` -- every prepared example returned no
# answer at all. Excluding it here does not weaken that check: an explicit
# caller override still applies and still fails closed on a genuine
# mismatch (pinned by
# ``tests/test_application_service.py::test_an_explicit_caller_override_of_provider_class_still_fails_closed_on_mismatch``),
# and the deployer remains responsible for configuring a provider whose
# declared class matches the default context they ship with -- exactly the
# stand-in relationship T10's runner already establishes for FakeProvider
# (see ``experiments/execution.py``'s provider_class note).
_EXAMPLE_OVERRIDE_FIELDS = (
    "domain",
    "purpose",
    "policy_version",
    "requester_role",
    "requested_pseudonym_scope",
)


def apply_example_governance_defaults(
    example: CorpusCaseInput, overrides: GovernanceOverrides
) -> GovernanceOverrides:
    """Layer ``example``'s own governance fields under ``overrides``,
    filling in only the fields ``overrides`` left ``None`` -- any explicit
    caller override always wins over the example's own value.
    """
    updates = {
        field_name: getattr(example, field_name)
        for field_name in _EXAMPLE_OVERRIDE_FIELDS
        if getattr(overrides, field_name) is None
    }
    if not updates:
        return overrides
    return dataclasses.replace(overrides, **updates)
