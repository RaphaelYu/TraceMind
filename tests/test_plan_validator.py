import pytest

from tm.ai.plan import PlanValidationError, validate_plan


def _base_plan():
    return {
        "version": "plan.v1",
        "goal": "Example goal",
        "constraints": {"max_steps": 5, "budget_usd": 0.05},
        "allow": {"tools": ["tool.sort"], "flows": ["flow.analyse"]},
        "steps": [
            {
                "id": "s1",
                "kind": "tool",
                "ref": "tool.sort",
                "inputs": {"items": [3, 2, 1]},
                "on_error": {"retry": {"max": 1, "backoff_ms": 500}},
            },
            {
                "id": "s2",
                "kind": "flow",
                "ref": "flow.analyse",
                "inputs": {"source": "${s1.results}"},
            },
        ],
    }


def test_validate_plan_accepts_valid_plan():
    plan = validate_plan(_base_plan())
    assert plan.goal == "Example goal"
    assert len(plan.steps) == 2
    assert plan.steps[0].ref == "tool.sort"
    assert plan.allow.tools == ("tool.sort",)


def test_validate_plan_rejects_missing_allow_reference():
    payload = _base_plan()
    payload["steps"][0]["ref"] = "tool.other"
    with pytest.raises(PlanValidationError) as exc:
        validate_plan(payload)
    assert "allow.tools" in str(exc.value)


def test_validate_plan_rejects_duplicate_step_ids():
    payload = _base_plan()
    payload["steps"][1]["id"] = "s1"
    with pytest.raises(PlanValidationError) as exc:
        validate_plan(payload)
    assert "Duplicate step id" in str(exc.value)


def test_validate_plan_rejects_unknown_top_level_field():
    payload = _base_plan()
    payload["unexpected"] = True
    with pytest.raises(PlanValidationError) as exc:
        validate_plan(payload)
    assert "Unexpected fields" in str(exc.value)


def test_validate_plan_rejects_invalid_kind():
    payload = _base_plan()
    payload["steps"][0]["kind"] = "unknown"
    with pytest.raises(PlanValidationError) as exc:
        validate_plan(payload)
    assert "must be one of" in str(exc.value)


def test_validate_plan_rejects_missing_steps():
    payload = _base_plan()
    payload["steps"] = []
    with pytest.raises(PlanValidationError):
        validate_plan(payload)
