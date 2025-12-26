from tm.intent import intent_precheck


def _capability_result_validated() -> dict:
    return {
        "capability_id": "validate.result",
        "version": "1.0.0",
        "inputs": {"value": {"type": "string", "required": True}},
        "event_types": [{"name": "validate.result.passed"}],
        "state_extractors": [
            {
                "from_event": "validate.result.passed",
                "produces": {
                    "result.validated": {"type": "boolean", "value": True},
                },
            }
        ],
        "safety_contract": {
            "determinism": True,
            "side_effects": ["none"],
            "rollback": {"supported": True},
        },
    }


def _base_policy() -> dict:
    return {
        "policy_id": "ref",
        "version": "1.0.0",
        "state_schema": {
            "result.validated": {"type": "boolean"},
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


def _intent(target: str = "result.validated", rule: str = "no_unvalidated_write") -> dict:
    return {
        "intent_id": "intent.validate.result",
        "version": "1.0.0",
        "goal": {"type": "achieve", "target": target},
        "constraints": [{"type": "safety", "rule": rule}],
    }


def test_precheck_valid_intent() -> None:
    result = intent_precheck(
        _intent(),
        policy=_base_policy(),
        capabilities=[_capability_result_validated()],
    )
    assert result.status == "valid"


def test_precheck_underconstrained_missing_state() -> None:
    result = intent_precheck(
        _intent(),
        policy=_base_policy(),
        capabilities=[],
    )
    assert result.status == "underconstrained"


def test_precheck_invalid_constraint() -> None:
    result = intent_precheck(
        _intent(rule="unknown_rule"),
        policy=_base_policy(),
        capabilities=[_capability_result_validated()],
    )
    assert result.status == "invalid"
    assert "unknown_rule" in result.reason


def test_precheck_overconstrained_by_invariant() -> None:
    policy = _base_policy()
    policy["invariants"].append(
        {
            "id": "forbid_validated",
            "type": "never",
            "condition": "result.validated",
        }
    )
    result = intent_precheck(
        _intent(),
        policy=policy,
        capabilities=[_capability_result_validated()],
    )
    assert result.status == "overconstrained"
