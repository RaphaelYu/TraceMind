from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from tm.artifacts import (
    ArtifactValidationError,
    validate_execution_trace,
    validate_workflow_policy,
)
from tm.policy import PolicyEvaluator
from tm.verifier import WorkflowVerificationReport, WorkflowVerifier
from tm.workflow.simulator import plan_workflow_steps


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_execution_entry(
    unit: str,
    capability_id: str,
    status: str,
    event: str,
    *,
    guard_status: str | None = None,
) -> Mapping[str, Any]:
    details: dict[str, Any] = {}
    if guard_status is not None:
        details["guard"] = guard_status
    return {
        "time": _timestamp(),
        "unit": unit,
        "status": status,
        "event": event,
        "details": details,
    }


class WorkflowExecutionError(RuntimeError):
    """Raised when the runtime cannot execute the workflow."""


class WorkflowVerificationError(WorkflowExecutionError):
    """Raised when a workflow fails verification before execution."""

    def __init__(self, report: WorkflowVerificationReport) -> None:
        self.report = report
        super().__init__("workflow verification failed")


def execute_workflow(
    workflow: Mapping[str, Any],
    *,
    policy: Mapping[str, Any],
    capabilities: Sequence[Mapping[str, Any]],
    guard_decisions: Mapping[str, bool] | None = None,
    events: Sequence[str] | None = None,
) -> Mapping[str, Any]:
    guard_decisions = dict(guard_decisions or {})
    pending_events = list(events or [])
    try:
        validate_workflow_policy(workflow)
    except ArtifactValidationError as exc:
        raise WorkflowExecutionError(f"workflow invalid: {exc}") from exc

    verifier = WorkflowVerifier(policy=policy, capabilities=capabilities)
    report = verifier.verify(workflow)
    if not report.success:
        raise WorkflowVerificationError(report)

    plans = plan_workflow_steps(workflow, capabilities)
    entries: list[Mapping[str, Any]] = []
    violations: list[str] = []
    state: dict[str, Any] = {}
    evaluator = PolicyEvaluator(policy)

    for plan in plans:
        guard = plan.guard
        status = "success"
        event_name = plan.events[-1] if plan.events else f"{plan.capability_id}.done"
        guard_status: str | None = None
        if guard:
            guard_name = guard.get("name")
            guard_decision = bool(guard_decisions.get(guard_name or ""))
            guard_status = "approved" if guard_decision else "denied"
            evaluation = evaluator.evaluate_guard(plan.capability_id, guard_decisions)
            if evaluation.violations:
                status = "guard-denied"
                event_name = f"{plan.capability_id}.guard_denied"
                violations.append(f"guard:{guard_name or plan.capability_id}")
                entries.append(
                    _make_execution_entry(
                        plan.step_id,
                        plan.capability_id,
                        status,
                        event_name,
                        guard_status=guard_status,
                    )
                )
                break
        state.update(plan.produces)
        entries.append(
            _make_execution_entry(
                plan.step_id,
                plan.capability_id,
                status,
                event_name,
                guard_status=guard_status,
            )
        )

    for extra_event in pending_events:
        entries.append(_make_execution_entry("event", "event", "success", extra_event))

    execution = {
        "trace_id": f"trace-{uuid.uuid4().hex}",
        "workflow_id": workflow.get("workflow_id", ""),
        "workflow_revision": workflow.get("version", "0"),
        "run_id": uuid.uuid4().hex,
        "intent_id": workflow.get("intent_id", ""),
        "timestamp": _timestamp(),
        "entries": entries,
        "state_snapshot": dict(state),
        "violations": violations,
        "metadata": {
            "guard_decisions": dict(guard_decisions),
            "events": pending_events,
        },
    }
    validate_execution_trace(execution)
    return execution
