from tm.runtime.reliability import (
    ReliabilityProfile,
    RunReliabilityController,
    cancel_run,
    clear_run_registry,
    list_runs,
    register_run,
)


def test_reliability_profile_parsing() -> None:
    meta = {
        "reliability": {
            "default": {"timeout_seconds": 30, "max_attempts": 2},
            "steps": {
                "observe": {"timeout_seconds": 5, "max_attempts": 1},
            },
        }
    }
    profile = ReliabilityProfile.from_meta(meta)
    assert profile.default_policy.timeout_seconds == 30
    assert profile.default_policy.max_attempts == 2
    observe = profile.policy_for_step("observe")
    assert observe.timeout_seconds == 5
    assert observe.max_attempts == 1
    random = profile.policy_for_step("unknown")
    assert random.timeout_seconds == 30
    assert random.max_attempts == 2


def test_run_registry_cancelation_flow() -> None:
    clear_run_registry()
    controller = RunReliabilityController(run_id="test-run", workspace_id="ws1")
    register_run("test-run", controller, workspace_id="ws1")
    states = list_runs("ws1")
    assert len(states) == 1
    state = cancel_run("test-run")
    assert state is not None
    assert state.canceled
    assert state.status == "cancelling"
    clear_run_registry()
