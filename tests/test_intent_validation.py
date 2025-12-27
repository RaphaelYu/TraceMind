from tm.cli.intent import evaluate_intent_status


def _capability_spec() -> dict:
    return {
        "capability_id": "compute.process",
        "version": "1.0.0",
        "inputs": {},
        "event_types": [{"name": "compute.process.done"}],
        "state_extractors": [
            {
                "from_event": "compute.process.done",
                "produces": {
                    "result.validated": {"type": "boolean"},
                },
            }
        ],
        "safety_contract": {
            "determinism": True,
            "side_effects": ["none"],
            "rollback": {"supported": False},
        },
    }


def _base_intent(goal: str) -> dict:
    return {
        "intent_id": "intent.validate.example",
        "version": "1.0.0",
        "goal": {"type": "achieve", "target": goal},
    }


def _base_policy(invariants=None) -> dict:
    policy = {
        "policy_id": "policy.example",
        "version": "1.0.0",
        "state_schema": {"result.validated": {"type": "boolean"}},
    }
    if invariants:
        policy["invariants"] = invariants
    return policy


def test_intent_validator_status_ok() -> None:
    intent = _base_intent("result.validated")
    policy = _base_policy()
    status, reason, details = evaluate_intent_status(intent, policy, [_capability_spec()])
    assert status == "OK"
    assert reason == "intent is composable"
    assert details["goal"] == "result.validated"


def test_intent_validator_status_underconstrained() -> None:
    intent = _base_intent("result.missing")
    policy = _base_policy()
    status, reason, _ = evaluate_intent_status(intent, policy, [_capability_spec()])
    assert status == "UNDERCONSTRAINED"
    assert "no capability produces state" in reason


def test_intent_validator_status_overconstrained() -> None:
    intent = _base_intent("result.validated")
    policy = _base_policy(invariants=[{"id": "no_result", "type": "never", "condition": "result.validated"}])
    status, reason, _ = evaluate_intent_status(intent, policy, [_capability_spec()])
    assert status == "OVERCONSTRAINED"
    assert "forbidden" in reason


def test_intent_validator_status_illegal_when_steps_present() -> None:
    intent = _base_intent("result.validated")
    intent["steps"] = [{"step_id": "step_compute"}]
    policy = _base_policy()
    status, reason, _ = evaluate_intent_status(intent, policy, [_capability_spec()])
    assert status == "ILLEGAL"
    assert "steps" in reason
