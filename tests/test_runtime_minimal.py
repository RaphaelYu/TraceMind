from tm.composer.reference import compose_reference_workflow
from tm.runtime.minimal import run_workflow


def _intent():
    return {
        "intent_id": "intent.reference",
        "version": "1.0.0",
        "goal": {"type": "achieve", "target": "result.validated"},
        "constraints": [{"type": "safety", "rule": "no_unvalidated_write"}],
    }


def _policy():
    return {
        "policy_id": "reference",
        "version": "1.0.0",
        "state_schema": {
            "result.validated": {"type": "boolean"},
            "external.write.performed": {"type": "boolean"},
        },
        "invariants": [
            {
                "id": "no_unvalidated_write",
                "type": "never",
                "condition": "external.write.performed && !result.validated",
            }
        ],
        "liveness": [],
    }


def _capabilities():
    compute = {
        "capability_id": "compute.process",
        "version": "1.0.0",
        "inputs": {"input_data": {"type": "string", "required": True}},
        "outputs": {"result": {"type": "string"}},
        "event_types": [{"name": "compute.process.done"}],
        "state_extractors": [
            {
                "from_event": "compute.process.done",
                "produces": {"computation.completed": {"type": "boolean", "value": True}},
            }
        ],
        "safety_contract": {"determinism": True, "side_effects": ["none"], "rollback": {"supported": True}},
    }
    validate = {
        "capability_id": "validate.result",
        "version": "1.0.0",
        "inputs": {"result": {"type": "string", "required": True}},
        "event_types": [{"name": "validate.result.passed"}],
        "state_extractors": [
            {
                "from_event": "validate.result.passed",
                "produces": {"result.validated": {"type": "boolean", "value": True}},
            }
        ],
        "safety_contract": {"determinism": True, "side_effects": ["none"], "rollback": {"supported": True}},
    }
    external = {
        "capability_id": "external.write",
        "version": "1.0.0",
        "inputs": {"payload": {"type": "string", "required": True}},
        "event_types": [{"name": "external.write.done"}],
        "state_extractors": [
            {
                "from_event": "external.write.done",
                "produces": {"external.write.performed": {"type": "boolean", "value": True}},
            }
        ],
        "safety_contract": {"determinism": False, "side_effects": ["external_io"], "rollback": {"supported": False}},
    }
    return [compute, validate, external]


def test_run_workflow_records_trace_without_violations():
    workflow = compose_reference_workflow(_intent(), policy=_policy(), capabilities=_capabilities())
    trace = run_workflow(workflow, guard_decisions={"external-write-approval": True})
    assert trace["violations"] == []
    assert trace["workflow_id"] == workflow["workflow_id"]
    assert any(entry["unit"] == "step_validate" for entry in trace["entries"])


def test_run_workflow_marks_guard_block_and_violation():
    workflow = compose_reference_workflow(_intent(), policy=_policy(), capabilities=_capabilities())
    trace = run_workflow(workflow, guard_decisions={"external-write-approval": False})
    assert "guard:external-write-approval" in trace["violations"]
    blocked_entries = [entry for entry in trace["entries"] if entry["status"] == "blocked"]
    assert blocked_entries


def test_run_workflow_appends_extra_events():
    workflow = compose_reference_workflow(_intent(), policy=_policy(), capabilities=_capabilities())
    extra_events = ["custom.event"]
    trace = run_workflow(workflow, guard_decisions={}, events=extra_events)
    assert trace["metadata"]["events"] == extra_events
