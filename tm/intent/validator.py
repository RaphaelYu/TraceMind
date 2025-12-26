from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from tm.artifacts import validate_intent_spec, validate_policy_spec

IntentStatus = str


@dataclass(frozen=True)
class IntentPrecheckResult:
    status: IntentStatus
    reason: str
    details: Mapping[str, Any] | None = None


def validate_intent(payload: Mapping[str, Any]) -> None:
    validate_intent_spec(payload)


def intent_precheck(
    intent: Mapping[str, Any],
    *,
    policy: Mapping[str, Any],
    capabilities: Sequence[Mapping[str, Any]] = (),
) -> IntentPrecheckResult:
    validate_intent_spec(intent)
    validate_policy_spec(policy)

    goal = intent["goal"]
    goal_target = str(goal["target"])
    capability_states = _collect_state_names_from_capabilities(capabilities)

    constraints = intent.get("constraints") or []
    invariants = policy.get("invariants") or []
    guards = policy.get("guards") or []
    invariant_ids = {str(inv["id"]) for inv in invariants if "id" in inv}
    guard_names = {str(guard.get("name")) for guard in guards if guard.get("name")}

    for constraint in constraints:
        rule = constraint.get("rule")
        if not rule:
            return IntentPrecheckResult(
                status="invalid",
                reason="constraint missing rule reference",
                details={"constraint": constraint},
            )
        if rule not in invariant_ids and rule not in guard_names:
            return IntentPrecheckResult(
                status="invalid",
                reason=f"constraint rule '{rule}' is not defined in policy invariants or guards",
                details={"constraint": constraint},
            )

    blocker = _find_goal_blocking_invariant(goal_target, invariants)
    if blocker:
        return IntentPrecheckResult(
            status="overconstrained",
            reason=f"goal '{goal_target}' is forbidden by invariant '{blocker['id']}'",
            details={"invariant": blocker},
        )

    if goal_target not in capability_states:
        return IntentPrecheckResult(
            status="underconstrained",
            reason=f"no capability produces state '{goal_target}'",
            details={"goal": goal_target},
        )

    return IntentPrecheckResult(status="valid", reason="intent is composable", details={"goal": goal_target})


def _collect_state_names_from_capabilities(capabilities: Iterable[Mapping[str, Any]]) -> set[str]:
    names: set[str] = set()
    for cap in capabilities:
        output = cap.get("outputs")
        if isinstance(output, Mapping):
            names.update(str(k) for k in output.keys())
        event_types = cap.get("event_types") or ()
        for event in event_types:
            if isinstance(event, Mapping) and "name" in event:
                names.add(str(event["name"]))
        for extractor in cap.get("state_extractors") or ():
            if isinstance(extractor, Mapping):
                produces = extractor.get("produces") or {}
                if isinstance(produces, Mapping):
                    names.update(str(k) for k in produces.keys())
    return names


def _find_goal_blocking_invariant(
    goal_target: str, invariants: Sequence[Mapping[str, Any]]
) -> Mapping[str, Any] | None:
    for inv in invariants:
        if inv.get("type") != "never":
            continue
        condition = str(inv.get("condition", ""))
        trimmed = condition.strip()
        contains_logic = "&&" in condition or "||" in condition

        if trimmed == goal_target:
            return inv

        if _condition_negates_goal(goal_target, condition) and not contains_logic:
            return inv
    return None


def _condition_negates_goal(goal_target: str, condition: str) -> bool:
    normalized = condition.replace(" ", "")
    return (
        normalized.startswith(f"!{goal_target}") or f"!{goal_target}" in normalized or f"not{goal_target}" in normalized
    )


__all__ = ["IntentPrecheckResult", "intent_precheck", "validate_intent"]
