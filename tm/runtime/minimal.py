from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Mapping

from tm.artifacts import validate_execution_trace


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_entry(
    step_id: str, capability_id: str, status: str, event: str, *, guard_status: str | None
) -> Dict[str, Any]:
    entry: Dict[str, Any] = {
        "time": _timestamp(),
        "unit": step_id,
        "status": status,
        "event": event,
        "details": {},
    }
    if guard_status:
        entry["details"]["guard"] = guard_status
    return entry


def run_workflow(
    workflow: Mapping[str, Any],
    *,
    guard_decisions: Mapping[str, bool] | None = None,
    events: Iterable[str] | None = None,
) -> Mapping[str, Any]:
    guard_decisions = guard_decisions or {}
    trace_entries: list[Dict[str, Any]] = []
    violations: list[str] = []
    state_snapshot: Dict[str, Any] = {}
    seen_validation = False

    for step in workflow.get("steps", []):
        step_id = str(step["step_id"])
        capability_id = str(step["capability_id"])
        guard = step.get("guard")
        guard_status = None
        status = "ok"
        event = f"{capability_id}.started"

        if guard:
            guard_name = guard.get("name")
            decision = guard_decisions.get(guard_name, True)
            guard_status = "approved" if decision else "rejected"
            if not decision:
                status = "blocked"
                violations.append(f"guard:{guard_name}")
                event = f"{capability_id}.guard_block"
        if status == "ok":
            if capability_id == "validate.result":
                seen_validation = True
            if capability_id == "external.write" and not seen_validation:
                violations.append("invariant:no_unvalidated_write")
                status = "error"
                event = "external.write.violation"
            else:
                event = f"{capability_id}.done"

        trace_entries.append(_make_entry(step_id, capability_id, status, event, guard_status=guard_status))

    if events:
        for ev in events:
            if ev not in [entry["event"] for entry in trace_entries]:
                trace_entries.append(
                    {
                        "time": _timestamp(),
                        "unit": "event",
                        "status": "ok",
                        "event": ev,
                        "details": {},
                    }
                )

    execution = {
        "trace_id": f"trace-{uuid.uuid4().hex}",
        "workflow_id": workflow["workflow_id"],
        "workflow_revision": workflow.get("version", "0"),
        "run_id": uuid.uuid4().hex,
        "intent_id": workflow["intent_id"],
        "timestamp": _timestamp(),
        "entries": trace_entries,
        "state_snapshot": state_snapshot,
        "violations": violations,
        "metadata": {"events": list(events or [])},
    }
    validate_execution_trace(execution)
    return execution
