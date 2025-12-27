import pytest

from tm.composer.reference import compose_reference_workflow
from tm.runtime.workflow_executor import (
    WorkflowExecutionError,
    WorkflowVerificationError,
    execute_workflow,
)


def _intent() -> dict:
    return {
        "intent_id": "intent.reference",
        "version": "1.0.0",
        "goal": {"type": "achieve", "target": "result.validated"},
    }


def _policy() -> dict:
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
                "required_for": ["external.write"],
            }
        ],
    }


def _capabilities() -> list[dict]:
    return [
        {
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
        },
        {
            "capability_id": "validate.result",
            "version": "1.0.0",
            "inputs": {"result": {"type": "string", "required": True}},
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
            "inputs": {"payload": {"type": "string", "required": True}},
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


def test_execute_workflow_emits_trace_for_approved_guard() -> None:
    policy = _policy()
    capabilities = _capabilities()
    workflow = compose_reference_workflow(_intent(), policy=policy, capabilities=capabilities)
    trace = execute_workflow(
        workflow,
        policy=policy,
        capabilities=capabilities,
        guard_decisions={"external-write-approval": True},
        events=["custom.event"],
    )
    assert trace["violations"] == []
    assert trace["metadata"]["guard_decisions"] == {"external-write-approval": True}
    assert trace["metadata"]["events"] == ["custom.event"]
    assert trace["state_snapshot"]["external.write.performed"] is True
    assert trace["entries"][-1]["event"] == "custom.event"


def test_execute_workflow_blocks_when_guard_denied() -> None:
    policy = _policy()
    capabilities = _capabilities()
    workflow = compose_reference_workflow(_intent(), policy=policy, capabilities=capabilities)
    trace = execute_workflow(
        workflow,
        policy=policy,
        capabilities=capabilities,
        guard_decisions={"external-write-approval": False},
    )
    assert trace["violations"] == ["guard:external-write-approval"]
    assert trace["state_snapshot"].get("external.write.performed") is None
    assert trace["entries"][-1]["status"] == "guard-denied"
    assert trace["entries"][-1]["details"].get("guard") == "denied"


def test_execute_workflow_requires_verified_candidate() -> None:
    policy = _policy()
    capabilities = _capabilities()
    workflow = compose_reference_workflow(_intent(), policy=policy, capabilities=capabilities)
    workflow["steps"] = [step for step in workflow["steps"] if step["capability_id"] != "validate.result"]
    with pytest.raises(WorkflowVerificationError) as excinfo:
        execute_workflow(
            workflow,
            policy=policy,
            capabilities=capabilities,
            guard_decisions={"external-write-approval": True},
        )
    counterexample = excinfo.value.report.counterexample or {}
    assert counterexample["violated_invariant"] == "inv.no_unvalidated_external_write"


def test_execute_workflow_errors_on_invalid_artifact() -> None:
    with pytest.raises(WorkflowExecutionError):
        execute_workflow(
            {"workflow_id": "bad"},
            policy=_policy(),
            capabilities=_capabilities(),
        )
