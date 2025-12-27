from tm.verifier import WorkflowVerifier


def _capability_spec(capability_id: str, produces: dict, side_effects=None, rollback=True):
    return {
        "capability_id": capability_id,
        "version": "v1",
        "inputs": {},
        "outputs": {},
        "event_types": [{"name": f"{capability_id}.done"}],
        "state_extractors": [
            {
                "from_event": f"{capability_id}.done",
                "produces": produces,
            }
        ],
        "safety_contract": {
            "determinism": True,
            "side_effects": side_effects or [],
            "rollback": {"supported": rollback},
        },
    }


def _build_workflow(include_validate=True):
    steps = [
        {"step_id": "step1", "capability_id": "compute.process"},
    ]
    if include_validate:
        steps.append({"step_id": "step2", "capability_id": "validate.result"})
    steps.append(
        {
            "step_id": "step3",
            "capability_id": "external.write",
            "guard": {
                "name": "external-write-approval",
                "type": "approval",
                "required_for": "external.write",
            },
        }
    )
    return {
        "workflow_id": "policy.reference.T1.example",
        "intent_id": "intent.ref",
        "policy_id": "policy.reference",
        "steps": steps,
        "transitions": [{"from": "step1", "to": "step2"}, {"from": "step2", "to": "step3"}],
        "guards": [{"name": "external-write-approval", "type": "approval", "required_for": "external.write"}],
    }


def _policy_spec():
    return {
        "policy_id": "policy.reference",
        "version": "1.0.0",
        "state_schema": {"result.validated": {"type": "boolean"}},
        "invariants": [{"id": "inv.no_unvalidated_external_write", "type": "never", "condition": "result.unvalidated"}],
    }


def _capabilities():
    return [
        _capability_spec(
            "compute.process",
            produces={
                "prediction.ready": {"type": "boolean", "value": True},
                "result.unvalidated": {"type": "boolean", "value": True},
            },
        ),
        _capability_spec(
            "validate.result",
            produces={
                "result.validated": {"type": "boolean", "value": True},
                "result.unvalidated": {"type": "boolean", "value": False},
            },
        ),
        _capability_spec(
            "external.write",
            produces={"external.write.performed": {"type": "boolean", "value": True}},
            side_effects=["external_io"],
            rollback=False,
        ),
    ]


def test_workflow_verifier_success():
    workflow = _build_workflow(include_validate=True)
    verifier = WorkflowVerifier(policy=_policy_spec(), capabilities=_capabilities())
    report = verifier.verify(workflow)
    assert report.success
    assert report.counterexample is None


def test_workflow_verifier_counterexample_for_unsat():
    workflow = _build_workflow(include_validate=False)
    verifier = WorkflowVerifier(policy=_policy_spec(), capabilities=_capabilities())
    report = verifier.verify(workflow)
    assert not report.success
    counterexample = report.counterexample or {}
    assert counterexample["violated_invariant"] == "inv.no_unvalidated_external_write"
    assert counterexample["steps"][-1]["capability_id"] == "external.write"
    assert counterexample["state_at_violation"]["result.unvalidated"]
