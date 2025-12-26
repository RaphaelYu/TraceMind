import pytest

from tm.composer.reference import ComposerError, compose_reference_workflow
from tm.verifier.reference import verify_reference_trace


def _capability_compute() -> dict:
    return {
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
        "safety_contract": {
            "determinism": True,
            "side_effects": ["none"],
            "rollback": {"supported": True},
        },
    }


def _capability_validate() -> dict:
    return {
        "capability_id": "validate.result",
        "version": "1.0.0",
        "inputs": {"value": {"type": "string", "required": True}},
        "event_types": [{"name": "validate.result.passed"}],
        "state_extractors": [
            {
                "from_event": "validate.result.passed",
                "produces": {"result.validated": {"type": "boolean", "value": True}},
            }
        ],
        "safety_contract": {
            "determinism": True,
            "side_effects": ["none"],
            "rollback": {"supported": True},
        },
    }


def _capability_external() -> dict:
    return {
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
        "safety_contract": {
            "determinism": False,
            "side_effects": ["external_io"],
            "rollback": {"supported": False},
        },
    }


def _policy() -> dict:
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


def _intent() -> dict:
    return {
        "intent_id": "intent.reference",
        "version": "1.0.0",
        "goal": {"type": "achieve", "target": "result.validated"},
        "constraints": [{"type": "safety", "rule": "no_unvalidated_write"}],
    }


def test_compose_reference_workflow() -> None:
    workflow = compose_reference_workflow(
        _intent(),
        policy=_policy(),
        capabilities=[_capability_compute(), _capability_validate(), _capability_external()],
    )
    assert workflow["workflow_id"].endswith(".reference")
    assert len(workflow["steps"]) == 3
    assert any(step.get("guard") for step in workflow["steps"])


def test_compose_reference_missing_capability() -> None:
    with pytest.raises(ComposerError):
        compose_reference_workflow(_intent(), policy=_policy(), capabilities=[_capability_compute()])


def test_reference_verifier_detects_violation() -> None:
    workflow = compose_reference_workflow(
        _intent(),
        policy=_policy(),
        capabilities=[_capability_compute(), _capability_validate(), _capability_external()],
    )
    report = verify_reference_trace(
        ["compute.process.done", "external.write.done"], workflow=workflow, policy=_policy()
    )
    assert report["status"] == "violated"
    assert "no_unvalidated_write" in report["violated_rules"]
    assert report["metadata"]["counterexample"] == ["compute.process.done", "external.write.done"]
    assert report["metadata"]["patch_proposal"]["source"] == "violation"


def test_reference_verifier_satisfied() -> None:
    workflow = compose_reference_workflow(
        _intent(),
        policy=_policy(),
        capabilities=[_capability_compute(), _capability_validate(), _capability_external()],
    )
    report = verify_reference_trace(
        ["compute.process.done", "validate.result.passed", "external.write.done"],
        workflow=workflow,
        policy=_policy(),
    )
    assert report["status"] == "satisfied"
    assert report["metadata"]["counterexample"] == [
        "compute.process.done",
        "validate.result.passed",
        "external.write.done",
    ]
    assert "patch_proposal" not in report["metadata"]
