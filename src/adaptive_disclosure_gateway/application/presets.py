"""Server-side governance presets: the one way an adapter may select a
domain/policy configuration (T20 / issue #28, demo-integration slice; issue
#41 gate A).

The problem this solves
-----------------------

``DisclosureApplicationService`` is constructed with one default
``GovernanceContext`` -- for the demo deployment, the HR one every prepared
example needs. A contract uploaded through the guided UI must NOT be
analysed under that default: ``hr-v1`` has no rule for ``party_name``,
``cnpj``, ``contract_value``, ``penalty_amount`` or ``deadline``, so a
contract run under it fails closed to BLOCK_REQUEST on every category and
the reviewer sees nothing (issue #41's blocker 4).

The obvious fix -- let the browser send ``domain``/``policy_version``/
``purpose`` as free strings on ``GovernanceOverrides`` -- is the wrong one.
``purpose`` is read by ``contracts-v1``'s ``purpose_actions``
(``financial_audit`` unlocks PRESERVE on ``contract_value``,
``compliance_review`` on ``penalty_amount``), and ``policy_version`` selects
the whole policy document. A client that can write those fields freely is a
client that decides governance. So this module inverts it: the caller names
a *document type* and an *analysis mode* from a fixed, server-owned
allowlist, and the server resolves which governance configuration that
means.

The contract with an adapter
----------------------------

- The caller sends two short, opaque tokens (``document_type``,
  ``analysis_mode``); neither is a policy identifier.
- An unregistered document type or an unlisted analysis mode raises
  ``DocumentAnalysisPresetError``. There is no default document type and no
  fallback preset: a caller that names nothing recognizable is refused, never
  silently served the HR configuration.
- The resolved ``GovernanceOverrides`` sets ``domain``, ``policy_version``,
  ``purpose`` and ``requester_role`` and nothing else.

What a preset deliberately does NOT set
---------------------------------------

``provider_class``: which class of provider a request may egress to is a
*deployment* fact, owned by whoever configured this service's ``Provider``
-- exactly the reasoning ``application/requests.py``'s
``_EXAMPLE_OVERRIDE_FIELDS`` already records for prepared examples, where an
example-supplied ``provider_class`` broke the guided flow outright. A preset
naming one would re-create that failure, and would also let a caller-facing
token weaken the fail-closed provider-class check at the provider boundary.

Lifecycle identifiers (``session_id``/``document_id``/``request_id``/
``requester_id``): these identify a real requester/session/document
lifecycle and belong to the deployer's ``default_context``, never to a
shared, reusable preset.

Why an analysis mode's name is the policy ``purpose`` verbatim
--------------------------------------------------------------

A mode is allowlisted by being listed in ``analysis_modes`` and is then used
as ``purpose`` unchanged. A translation table between "UI vocabulary" and
"policy vocabulary" was deliberately not introduced: it would be a second
vocabulary to keep synchronized with ``configs/policies/*.yaml``, and a
drifted entry would silently select the wrong action space. The allowlist,
not a rename, is what stops a client inventing a purpose. Human-readable
labels for these tokens belong in the UI's own copy layer (``web/lib/copy.ts``),
not here.

No-leak invariant (CLAUDE.md): ``DocumentAnalysisPresetError`` names only
the supported options -- never the caller-supplied token, which is
attacker-controlled text arriving on the same request as the document.
"""

from __future__ import annotations

from dataclasses import dataclass

from adaptive_disclosure_gateway.application.contracts import GovernanceOverrides

CONTRACT_DOCUMENT_TYPE = "contract"
"""The advisor demo's primary document type (issue #41 gate B)."""

HR_RECORD_DOCUMENT_TYPE = "hr_record"
"""The HR pilot configuration, expressed as a preset like any other.

Present so the mechanism is a registry rather than a Contracts special case,
and so that "the server's HR default" is something a caller must ask for by
name instead of something it falls back to.
"""


class DocumentAnalysisPresetError(Exception):
    """Raised when a caller names a document type or analysis mode that is
    not in this module's allowlist.

    Messages name the supported options only -- never the token the caller
    sent. See the module docstring's no-leak note.
    """


@dataclass(frozen=True)
class DocumentAnalysisPreset:
    """One server-owned mapping from a caller-facing document type onto a
    governance configuration.

    ``analysis_modes`` is the complete allowlist of ``purpose`` values a
    caller may select for this document type; ``analysis_modes[0]`` is the
    default when the caller names none. Every entry must be a purpose the
    corresponding policy document actually understands -- a mode that no
    ``purpose_actions`` block mentions is still legitimate (it selects the
    rule's ``default``/``allowed_actions`` branch), but an invented one would
    be a governance claim nothing enforces.
    """

    document_type: str
    domain: str
    policy_version: str
    requester_role: str
    analysis_modes: tuple[str, ...]

    @property
    def default_analysis_mode(self) -> str:
        return self.analysis_modes[0]


_CONTRACT_PRESET = DocumentAnalysisPreset(
    document_type=CONTRACT_DOCUMENT_TYPE,
    domain="contracts",
    policy_version="contracts-v1",
    # contracts-v1 declares no requester_role condition and no
    # pseudonym_scope block, so this role is inert for policy resolution
    # today. It is set explicitly anyway so the audit/governance view records
    # who the request claimed to be, and so a future contracts-v2 that does
    # read the role has a value to read rather than None.
    requester_role="contract_analyst",
    # `contract_summary` first: it is the default the guided UI uses, and it
    # is deliberately the LEAST disclosing of the three -- it appears in no
    # `purpose_actions` block in contracts-v1, so contract_value and
    # penalty_amount keep their default (remove, generalize) action space.
    # The two audit/review modes each unlock PRESERVE on exactly one of those
    # categories and neither unlocks the other (see
    # docs/contracts-policy-matrix.md).
    analysis_modes=("contract_summary", "financial_audit", "compliance_review"),
)

_HR_RECORD_PRESET = DocumentAnalysisPreset(
    document_type=HR_RECORD_DOCUMENT_TYPE,
    domain="hr",
    policy_version="hr-v1",
    requester_role="hr_analyst",
    analysis_modes=("team_summary", "salary_analysis", "compensation_review"),
)

_PRESETS: dict[str, DocumentAnalysisPreset] = {
    preset.document_type: preset for preset in (_CONTRACT_PRESET, _HR_RECORD_PRESET)
}


def list_document_presets() -> tuple[DocumentAnalysisPreset, ...]:
    """Every registered preset, in registration order. Pure data -- an
    adapter may surface these so a UI can render the available document
    types without hardcoding them.
    """
    return tuple(_PRESETS.values())


def get_document_preset(document_type: str) -> DocumentAnalysisPreset:
    """The preset registered for ``document_type``.

    Raises ``DocumentAnalysisPresetError`` for anything else. Matching is
    exact: no normalization, no case folding and no whitespace stripping, so
    a caller cannot reach a preset by a spelling this module never
    registered.
    """
    preset = _PRESETS.get(document_type)
    if preset is None:
        raise DocumentAnalysisPresetError(
            f"unsupported document type; supported document types: {tuple(sorted(_PRESETS))!r}"
        )
    return preset


def resolve_governance_preset(
    document_type: str, *, analysis_mode: str | None
) -> GovernanceOverrides:
    """Resolve a caller-facing ``(document_type, analysis_mode)`` pair into
    the ``GovernanceOverrides`` the application service applies over the
    deployer's default context.

    ``analysis_mode=None`` selects the preset's own default mode. Any other
    value must appear verbatim in the preset's ``analysis_modes`` allowlist.
    """
    preset = get_document_preset(document_type)

    if analysis_mode is None:
        purpose = preset.default_analysis_mode
    elif analysis_mode in preset.analysis_modes:
        purpose = analysis_mode
    else:
        raise DocumentAnalysisPresetError(
            "unsupported analysis mode for this document type; supported analysis modes: "
            f"{preset.analysis_modes!r}"
        )

    return GovernanceOverrides(
        domain=preset.domain,
        policy_version=preset.policy_version,
        purpose=purpose,
        requester_role=preset.requester_role,
    )
