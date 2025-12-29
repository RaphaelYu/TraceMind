from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from tm.agents.models import EffectRef
from tm.runtime.context import ExecutionContext
from tm.policy.policies_v0 import DEFAULT_ALLOWLIST, policy_allowlist


@dataclass
class PolicyDecision:
    effect_name: str
    target: str
    allowed: bool
    reason: str


class PolicyGuard:
    def __init__(self, allowlist: Sequence[str] | None = None) -> None:
        self._global_allowlist = set(allowlist or DEFAULT_ALLOWLIST)

    def evaluate(
        self,
        effect: EffectRef,
        context: ExecutionContext,
        bundle_meta: Mapping[str, object] | None = None,
    ) -> PolicyDecision:
        allowlist = set(self._global_allowlist)
        meta_allow = self._allowlist_from_meta(bundle_meta)
        allowlist.update(meta_allow)
        allowed = effect.target in allowlist
        reason = "allowed by policy" if allowed else "target not allowlisted"
        context.record_audit("policy_guard", {"effect": effect.name, "target": effect.target, "allowed": allowed})
        context.evidence.record(
            "policy_guard",
            {"effect": effect.name, "target": effect.target, "allowed": allowed, "reason": reason},
        )
        return PolicyDecision(effect_name=effect.name, target=effect.target, allowed=allowed, reason=reason)

    def _allowlist_from_meta(self, meta: Mapping[str, object] | None) -> Sequence[str]:
        return policy_allowlist(meta)
