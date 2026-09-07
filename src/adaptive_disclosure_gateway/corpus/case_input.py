"""The privileged half of a corpus case: everything a disclosure treatment
may legitimately see (T09 / issue #4, Phase A).

``CorpusCaseInput`` is the *only* type in this package with a method that
builds a ``DisclosureRequest`` -- see
``tests/test_corpus_oracle_isolation.py``, which pins that by AST
inspection rather than trusting this docstring. ``CaseOracle``
(``oracle.py``) has no such method and no path into the pipeline at all.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from adaptive_disclosure_gateway.corpus.models import TaskFamily
from adaptive_disclosure_gateway.domain import DisclosureRequest, GovernanceContext, PseudonymScope


class CorpusCaseInput(BaseModel):
    """Everything a treatment may legitimately see for one corpus case:
    ``sample_id``, the controlled text, the task/instruction, and the
    ``GovernanceContext`` fields the case exercises.

    ``task_family`` is metadata for corpus-coverage reporting only -- it is
    never part of ``GovernanceContext`` and never reaches
    ``to_disclosure_request()``'s output.
    """

    model_config = ConfigDict(extra="forbid")

    sample_id: str = Field(min_length=1)
    text: str
    task: str
    task_family: TaskFamily

    # GovernanceContext fields the case exercises. Optional ones default
    # exactly like GovernanceContext itself so a case only needs to state
    # what it actually varies.
    domain: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    requester_role: str | None = None
    requester_id: str | None = None
    provider_class: str = "external_llm"
    policy_version: str = Field(min_length=1)
    requested_pseudonym_scope: PseudonymScope = PseudonymScope.SESSION
    request_id: str | None = None
    document_id: str | None = None
    session_id: str | None = None

    def to_disclosure_request(self) -> DisclosureRequest:
        """Build the ``DisclosureRequest`` a treatment actually runs against.

        Reads only fields declared above -- never anything from a
        ``CaseOracle`` (there is no ``CaseOracle`` reference reachable from
        here at all; see ``tests/test_corpus_oracle_isolation.py``).
        """
        context = GovernanceContext(
            domain=self.domain,
            purpose=self.purpose,
            requester_role=self.requester_role,
            requester_id=self.requester_id,
            provider_class=self.provider_class,
            policy_version=self.policy_version,
            requested_pseudonym_scope=self.requested_pseudonym_scope,
            request_id=self.request_id,
            document_id=self.document_id,
            session_id=self.session_id,
        )
        return DisclosureRequest(text=self.text, task=self.task, context=context)
