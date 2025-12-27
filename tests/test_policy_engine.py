from tm.policy import PolicyEvaluator


def _policy_spec() -> dict:
    return {
        "policy_id": "policy.examples",
        "version": "1.0.0",
        "state_schema": {"result.validated": {"type": "boolean"}},
        "invariants": [
            {"id": "no_unvalidated_write", "type": "never", "condition": "result.unvalidated"},
        ],
        "guards": [
            {
                "name": "external-write-approval",
                "type": "approval",
                "scope": "workflow",
                "required_for": "external.write",
            },
        ],
    }


def test_policy_evaluator_detects_invariant_violation() -> None:
    evaluator = PolicyEvaluator(_policy_spec())
    result = evaluator.check_state({"result.unvalidated": True})
    assert not result.succeeded
    violation = result.violations[0]
    assert violation.kind == "invariant"
    assert violation.rule_id == "no_unvalidated_write"
    assert violation.evidence["state_key"] == "result.unvalidated"


def test_policy_evaluator_guard_requires_decision() -> None:
    evaluator = PolicyEvaluator(_policy_spec())
    result = evaluator.evaluate_guard("external.write", guard_decisions={})
    assert not result.succeeded
    violation = result.violations[0]
    assert violation.kind == "guard"
    assert violation.rule_id == "external-write-approval"


def test_policy_evaluator_guard_satisfied_when_decision_true() -> None:
    evaluator = PolicyEvaluator(_policy_spec())
    result = evaluator.evaluate_guard("external.write", guard_decisions={"external-write-approval": True})
    assert result.succeeded


def test_policy_evaluator_combines_state_and_guard() -> None:
    evaluator = PolicyEvaluator(_policy_spec())
    trace = {"state_snapshot": {"result.unvalidated": True}, "capability_id": "external.write"}
    result = evaluator.check_trace(trace, guard_decisions={})
    assert len(result.violations) == 2
