from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from tm.artifacts import validate_integrated_state_report, validate_patch_proposal


@dataclass(frozen=True)
class ViolationContext:
    invariant_id: str
    evidence: Sequence[str]
    blame_capability: str


def verify_reference_trace(
    events: Sequence[str],
    *,
    workflow: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> Mapping[str, Any]:
    seen_validation = False
    events_list = list(events)
    for idx, ev in enumerate(events_list):
        if ev == "validate.result.passed":
            seen_validation = True
        if ev == "external.write.done" and not seen_validation:
            context = _find_violation_context(policy)
            seen_events = events_list[: idx + 1]
            report = _build_report(workflow, context, status="violated", events=seen_events, evidence=seen_events)
            report["metadata"]["counterexample"] = list(events_list)
            report["metadata"]["patch_proposal"] = _build_patch_proposal(workflow, context)
            validate_integrated_state_report(report)
            return report

    report = _build_report(workflow, None, status="satisfied", events=events_list, evidence=events_list)
    report["metadata"]["counterexample"] = list(events_list)
    validate_integrated_state_report(report)
    return report


def _find_violation_context(policy: Mapping[str, Any]) -> ViolationContext:
    invariants = policy.get("invariants") or ()
    for inv in invariants:
        if inv.get("id") and "result.validated" in str(inv.get("condition", "")):
            return ViolationContext(invariant_id=str(inv["id"]), evidence=[], blame_capability="external.write")
    return ViolationContext(invariant_id="unknown", evidence=[], blame_capability="external.write")


def _build_report(
    workflow: Mapping[str, Any],
    context: ViolationContext | None,
    *,
    status: str,
    events: Sequence[str],
    evidence: Sequence[str],
) -> Mapping[str, Any]:
    report_id = str(uuid.uuid4())
    violated_rules: list[str] = []
    blame: dict[str, str] | None = None
    if context:
        violated_rules = [context.invariant_id]
        blame = {"capability": context.blame_capability}
    else:
        violated_rules = []
        blame = {}

    snapshot = _derive_state(events)

    report = {
        "report_id": report_id,
        "workflow_id": workflow["workflow_id"],
        "intent_id": workflow["intent_id"],
        "status": status,
        "state_snapshot": snapshot,
        "violated_rules": violated_rules,
        "evidence": list(evidence),
        "blame": blame,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metadata": {
            "events": list(events),
        },
    }

    if context and "external.write.done" in events:
        blame["guard"] = "approved"

    return report


def _build_patch_proposal(workflow: Mapping[str, Any], context: ViolationContext) -> Mapping[str, Any]:
    proposal = {
        "proposal_id": f"{workflow['workflow_id']}-patch",
        "source": "violation",
        "target": "policy",
        "description": "Enforce validation guard before external write",
        "rationale": f"Violation of invariant {context.invariant_id}",
        "expected_effect": "Prevent external writes without validation",
        "changes": [
            {
                "path": "guards",
                "op": "set",
                "value": [
                    {
                        "name": "external-write-approval",
                        "type": "approval",
                        "scope": "workflow",
                        "required_for": "external.write",
                    }
                ],
            }
        ],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "metadata": {"workflow_id": workflow["workflow_id"]},
    }
    validate_patch_proposal(proposal)
    return proposal


def _derive_state(events: Sequence[str]) -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    validated = any(ev.startswith("validate.result") for ev in events)
    snapshot["result.validated"] = validated
    snapshot["result.unvalidated"] = not validated
    if any(ev.startswith("external.write") for ev in events):
        snapshot["external.write.performed"] = True
    return snapshot


__all__ = ["verify_reference_trace", "ViolationContext"]
