from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

from tm.artifacts import validate_integrated_state_report
from tm.policy import PolicyEvaluator
from tm.workflow.simulator import MissingCapabilityError, plan_workflow_steps


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class IntegratedStateReportError(RuntimeError):
    """Raised when building an IntegratedStateReport fails."""


def _group_trace_entries(entries: Iterable[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    mapping: dict[str, Mapping[str, Any]] = {}
    for entry in entries:
        unit = entry.get("unit")
        if not isinstance(unit, str):
            continue
        mapping[unit] = entry
    return mapping


def build_integrated_state_report(
    trace: Mapping[str, Any],
    *,
    workflow: Mapping[str, Any],
    policy: Mapping[str, Any],
    capabilities: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    entries = trace.get("entries") or []
    step_entries = _group_trace_entries(entries)
    try:
        plans = plan_workflow_steps(workflow, capabilities)
    except MissingCapabilityError as exc:
        raise IntegratedStateReportError(f"missing capability: {exc}") from exc

    state: dict[str, Any] = {}
    evaluator = PolicyEvaluator(policy)
    evidence_events: list[str] = []

    for plan in plans:
        entry = step_entries.get(plan.step_id)
        event_name = entry.get("event") if isinstance(entry, Mapping) else None
        if isinstance(event_name, str) and event_name:
            evidence_events.append(event_name)
        state.update(plan.produces)

    evaluation = evaluator.check_state(state)
    status = "violated" if not evaluation.succeeded else "satisfied"
    report_id = f"state-{uuid.uuid4().hex}"
    snapshot = dict(state)
    report: dict[str, Any] = {
        "report_id": report_id,
        "workflow_id": workflow.get("workflow_id", ""),
        "intent_id": workflow.get("intent_id", ""),
        "status": status,
        "timestamp": _timestamp(),
        "state_snapshot": snapshot,
        "metadata": {
            "trace_id": trace.get("trace_id"),
            "events": list(evidence_events),
        },
    }

    if not evaluation.succeeded and evaluation.violations:
        violation = evaluation.violations[0]
        last_plan = plans[-1] if plans else None
        last_entry = step_entries.get(last_plan.step_id) if last_plan else {}
        report["violated_rules"] = [violation.rule_id]
        report["evidence"] = list(evidence_events)
        blame: dict[str, Any] = {
            "capability": last_plan.capability_id if last_plan else "",
            "policy": policy.get("policy_id", ""),
            "step": last_plan.step_id if last_plan else "",
        }
        guard = last_entry.get("details", {}).get("guard") if isinstance(last_entry, Mapping) else None
        if guard:
            blame["guard"] = guard
        report["blame"] = blame

    validate_integrated_state_report(report)
    return report
