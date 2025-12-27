from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from tm.policy import PolicyEvaluator
from tm.workflow.simulator import MissingCapabilityError, build_state_trace


@dataclass(frozen=True)
class WorkflowCounterexample:
    steps: Sequence[Mapping[str, Any]]
    violated_invariant: str
    violation_detail: str
    condition: str
    step_index: int
    capability_id: str
    state_snapshot: Mapping[str, Any]

    def to_dict(self) -> Mapping[str, Any]:
        return {
            "steps": [dict(step) for step in self.steps],
            "violated_invariant": self.violated_invariant,
            "violation_detail": self.violation_detail,
            "condition": self.condition,
            "step_index": self.step_index,
            "capability_id": self.capability_id,
            "state_at_violation": dict(self.state_snapshot),
        }


@dataclass(frozen=True)
class WorkflowVerificationReport:
    success: bool
    counterexample: Mapping[str, Any] | None


class WorkflowVerifier:
    def __init__(self, policy: Mapping[str, Any], capabilities: Sequence[Mapping[str, Any]]):
        self.policy_engine = PolicyEvaluator(policy)
        self.capabilities = {
            str(spec.get("capability_id")): spec
            for spec in capabilities
            if isinstance(spec, Mapping) and spec.get("capability_id")
        }

    def verify(self, workflow: Mapping[str, Any]) -> WorkflowVerificationReport:
        try:
            trace, state = build_state_trace(workflow, list(self.capabilities.values()))
        except MissingCapabilityError as exc:
            return WorkflowVerificationReport(
                success=False,
                counterexample={
                    "reason": "MISSING_CAPABILITY",
                    "capability_id": exc.capability_id,
                    "step_id": exc.step_id,
                },
            )
        if trace:
            evaluation = self.policy_engine.check_state(state)
            if not evaluation.succeeded:
                violation = evaluation.violations[0]
                last_step = trace[-1]
                counterexample = WorkflowCounterexample(
                    steps=trace,
                    violated_invariant=violation.rule_id,
                    violation_detail=violation.detail,
                    condition=violation.detail,
                    step_index=len(trace) - 1,
                    capability_id=last_step.get("capability_id") or "",
                    state_snapshot=state,
                )
                return WorkflowVerificationReport(success=False, counterexample=counterexample.to_dict())
        return WorkflowVerificationReport(success=True, counterexample=None)
