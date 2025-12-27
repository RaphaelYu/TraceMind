import pytest

from tm.composer.reference import compose_reference_workflow
from tm.monitoring.report import build_integrated_state_report, IntegratedStateReportError
from tm.runtime.workflow_executor import execute_workflow


def _intent():
    return {
        "intent_id": "intent.reference",
        "version": "1.0.0",
        "goal": {"type": "achieve", "target": "result.validated"},
    }


def _policy():
    return {
        "policy_id": "policy.reference",
        "version": "1.0.0",
        "state_schema": {
            "result.validated": {"type": "boolean"},
            "external.write.performed": {"type": "boolean"},
        },
        "invariants": [{"id": "inv.no_unvalidated_external_write", "type": "never", "condition": "result.unvalidated"}],
        "guards": [
            {
                "name": "external-write-approval",
                "type": "approval",
                "scope": "workflow",
                "required_for": "external.write",
            }
        ],
    }


def _capabilities():
    return [
        {
            "capability_id": "compute.process",
            "version": "1.0.0",
            "inputs": {},
            "outputs": {},
            "event_types": [{"name": "compute.process.done"}],
            "state_extractors": [
                {
                    "from_event": "compute.process.done",
                    "produces": {"computation.completed": {"type": "boolean", "value": True}},
                }
            ],
            "safety_contract": {"determinism": True, "side_effects": ["none"], "rollback": {"supported": True}},
        },
        {
            "capability_id": "validate.result",
            "version": "1.0.0",
            "inputs": {},
            "outputs": {},
            "event_types": [{"name": "validate.result.done"}],
            "state_extractors": [
                {
                    "from_event": "validate.result.done",
                    "produces": {
                        "result.validated": {"type": "boolean", "value": True},
                        "result.unvalidated": {"type": "boolean", "value": False},
                    },
                }
            ],
            "safety_contract": {"determinism": True, "side_effects": ["none"], "rollback": {"supported": True}},
        },
        {
            "capability_id": "external.write",
            "version": "1.0.0",
            "inputs": {},
            "outputs": {},
            "event_types": [{"name": "external.write.done"}],
            "state_extractors": [
                {
                    "from_event": "external.write.done",
                    "produces": {"external.write.performed": {"type": "boolean", "value": True}},
                }
            ],
            "safety_contract": {"determinism": True, "side_effects": ["external_io"], "rollback": {"supported": False}},
        },
    ]


def test_build_integrated_state_report_from_verified_trace() -> None:
    policy = _policy()
    capabilities = _capabilities()
    workflow = compose_reference_workflow(_intent(), policy=policy, capabilities=capabilities)
    trace = execute_workflow(
        workflow,
        policy=policy,
        capabilities=capabilities,
        guard_decisions={"external-write-approval": True},
    )
    report = build_integrated_state_report(
        trace,
        workflow=workflow,
        policy=policy,
        capabilities=capabilities,
    )
    assert report["status"] == "satisfied"
    assert report["state_snapshot"]["external.write.performed"] is True
    assert "violated_rules" not in report
    assert report["metadata"]["trace_id"] == trace["trace_id"]


def test_build_integrated_state_report_captures_violation() -> None:
    policy = _policy()
    capabilities = _capabilities()
    workflow = compose_reference_workflow(_intent(), policy=policy, capabilities=capabilities)
    workflow["steps"] = [step for step in workflow["steps"] if step["capability_id"] != "validate.result"]
    workflow["guards"] = [
        {
            "name": "external-write-approval",
            "type": "approval",
            "scope": "workflow",
            "required_for": "external.write",
        }
    ]
    trace = {
        "trace_id": "trace-violated",
        "workflow_id": workflow["workflow_id"],
        "run_id": "run-violated",
        "intent_id": workflow["intent_id"],
        "timestamp": "2024-01-01T00:00:00Z",
        "entries": [
            {
                "time": "2024-01-01T00:00:00Z",
                "unit": "step_compute",
                "status": "success",
                "event": "compute.process.done",
                "details": {},
            },
            {
                "time": "2024-01-01T00:00:01Z",
                "unit": "step_write",
                "status": "success",
                "event": "external.write.done",
                "details": {"guard": "approved"},
            },
        ],
        "state_snapshot": {"external.write.performed": True},
        "violations": [],
        "metadata": {},
    }
    report = build_integrated_state_report(
        trace,
        workflow=workflow,
        policy=policy,
        capabilities=capabilities,
    )
    assert report["status"] == "violated"
    assert report["violated_rules"] == ["inv.no_unvalidated_external_write"]
    assert report["evidence"] == ["compute.process.done", "external.write.done"]
    assert report["blame"]["capability"] == "external.write"
    assert report["blame"]["guard"] == "approved"


def test_build_integrated_state_report_missing_capability_fails() -> None:
    policy = _policy()
    capabilities = _capabilities()[:-1]
    workflow = {
        "workflow_id": "policy.reference.violation",
        "intent_id": _intent()["intent_id"],
        "policy_id": policy["policy_id"],
        "steps": [
            {"step_id": "step_external", "capability_id": "external.write"},
        ],
    }
    trace = {
        "trace_id": "trace-missing",
        "workflow_id": workflow["workflow_id"],
        "run_id": "run-missing",
        "intent_id": workflow["intent_id"],
        "timestamp": "2024-01-01T00:00:00Z",
        "entries": [
            {
                "time": "2024-01-01T00:00:00Z",
                "unit": "step_external",
                "status": "success",
                "event": "external.write.done",
                "details": {},
            }
        ],
        "state_snapshot": {"external.write.performed": True},
        "violations": [],
        "metadata": {},
    }
    with pytest.raises(IntegratedStateReportError):
        build_integrated_state_report(
            trace,
            workflow=workflow,
            policy=policy,
            capabilities=capabilities,
        )
