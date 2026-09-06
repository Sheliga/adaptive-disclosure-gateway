from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError

from adaptive_disclosure_gateway.domain import (
    DisclosureAction,
    GovernanceContext,
    PolicyDecision,
    PseudonymScope,
)

_SCOPE_RANK = {
    PseudonymScope.REQUEST: 0,
    PseudonymScope.DOCUMENT: 1,
    PseudonymScope.SESSION: 2,
    PseudonymScope.ORGANIZATION: 3,
}


class PolicyOverride(BaseModel):
    action: DisclosureAction
    purpose: str | None = None
    requester_role: str | None = None
    provider_class: str | None = None
    allowed_actions: list[DisclosureAction] = Field(default_factory=list)

    def matches(self, context: GovernanceContext) -> bool:
        checks = (
            self.purpose is None or self.purpose == context.purpose,
            self.requester_role is None or self.requester_role == context.requester_role,
            self.provider_class is None or self.provider_class == context.provider_class,
        )
        return all(checks)


class PolicyRule(BaseModel):
    default: DisclosureAction
    allowed_actions: list[DisclosureAction] = Field(default_factory=list)
    purpose_actions: dict[str, list[DisclosureAction]] = Field(default_factory=dict)
    overrides: list[PolicyOverride] = Field(default_factory=list)


class PseudonymScopePolicy(BaseModel):
    default: PseudonymScope = PseudonymScope.SESSION
    role_max: dict[str, PseudonymScope] = Field(default_factory=dict)
    user_max: dict[str, PseudonymScope] = Field(default_factory=dict)


class PolicyDocument(BaseModel):
    version: str
    domain: str
    rules: dict[str, PolicyRule]
    pseudonym_scope: PseudonymScopePolicy = Field(default_factory=PseudonymScopePolicy)


class PolicyRepository:
    def __init__(
        self,
        policies: dict[str, PolicyDocument] | None = None,
        load_errors: dict[str, str] | None = None,
    ) -> None:
        self._policies = policies or {}
        self._load_errors = load_errors or {}

    @classmethod
    def from_directory(cls, directory: str | Path) -> PolicyRepository:
        policies: dict[str, PolicyDocument] = {}
        errors: dict[str, str] = {}

        for path in sorted(Path(directory).glob("*.yaml")):
            try:
                raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
                policy = PolicyDocument.model_validate(raw)
            except (OSError, yaml.YAMLError, ValidationError, TypeError) as exc:
                errors[path.name] = str(exc)
                continue

            if policy.version in policies:
                errors[path.name] = f"duplicate policy version: {policy.version}"
                policies.pop(policy.version, None)
                continue

            policies[policy.version] = policy

        return cls(policies=policies, load_errors=errors)

    def decide(self, context: GovernanceContext, category: str) -> PolicyDecision:
        policy = self._policies.get(context.policy_version)
        if policy is None:
            return self._block(category, context, "Policy version is missing or failed to load")

        if policy.domain != context.domain:
            return self._block(category, context, "Policy domain does not match governance context")

        rule = policy.rules.get(category)
        if rule is None:
            return self._block(category, context, "Missing rule for sensitive category")

        matching_overrides = [override for override in rule.overrides if override.matches(context)]
        if len(matching_overrides) > 1:
            return self._block(category, context, "Ambiguous policy overrides")

        if matching_overrides:
            override = matching_overrides[0]
            action = override.action
            allowed_actions = list(override.allowed_actions)
            reason = "Matched explicit contextual policy override"
        else:
            action = rule.default
            allowed_actions = list(rule.allowed_actions)
            reason = "Applied deterministic default policy rule"

        if action is DisclosureAction.TASK_DEPENDENT:
            allowed_actions = list(rule.purpose_actions.get(context.purpose, allowed_actions))
            if not allowed_actions:
                return self._block(
                    category,
                    context,
                    "Task-dependent rule has no permitted action space",
                )
            reason = "Task-dependent decision constrained to policy-permitted actions"

        return PolicyDecision(
            category=category,
            action=action,
            reason=reason,
            allowed_actions=allowed_actions,
            policy_version=policy.version,
        )

    def resolve_pseudonym_scope(self, context: GovernanceContext) -> PseudonymScope:
        policy = self._policies.get(context.policy_version)
        if policy is None or policy.domain != context.domain:
            return PseudonymScope.REQUEST

        scope_policy = policy.pseudonym_scope
        ceiling = scope_policy.default

        if context.requester_role is not None:
            ceiling = scope_policy.role_max.get(context.requester_role, ceiling)
        if context.requester_id is not None:
            ceiling = scope_policy.user_max.get(context.requester_id, ceiling)

        requested = context.requested_pseudonym_scope
        return requested if _SCOPE_RANK[requested] <= _SCOPE_RANK[ceiling] else ceiling

    @property
    def load_errors(self) -> dict[str, str]:
        return dict(self._load_errors)

    @staticmethod
    def _block(
        category: str,
        context: GovernanceContext,
        reason: str,
    ) -> PolicyDecision:
        return PolicyDecision(
            category=category,
            action=DisclosureAction.BLOCK_REQUEST,
            reason=reason,
            policy_version=context.policy_version,
        )
