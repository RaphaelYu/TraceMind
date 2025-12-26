from tm.iteration.loop import IterationResult, apply_patch_proposal, run_iteration


def _policy() -> dict:
    return {
        "policy_id": "reference",
        "version": "1.0.0",
        "state_schema": {"a": {"type": "boolean"}},
    }


def _patch() -> dict:
    return {
        "proposal_id": "p1",
        "source": "violation",
        "target": "policy",
        "description": "Add guard",
        "rationale": "Test",
        "expected_effect": "Guard inserted",
        "changes": [
            {
                "path": "guards",
                "op": "set",
                "value": [{"name": "external-write-approval", "type": "approval"}],
            }
        ],
    }


def test_apply_patch_proposal_updates_policy() -> None:
    policy = _policy()
    updated = apply_patch_proposal(policy, _patch())
    assert updated["version"] == "1.0.1"
    assert updated["guards"][0]["name"] == "external-write-approval"


def test_run_iteration_returns_result() -> None:
    policy = _policy()
    proposal = _patch()
    result: IterationResult = run_iteration(policy, patch_proposal=proposal, approval="auto")
    assert result.policy["version"] == "1.0.1"
    assert result.applied_patch["proposal_id"] == "p1"
    assert result.approval == "auto"
