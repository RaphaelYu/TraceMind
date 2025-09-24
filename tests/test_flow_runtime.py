import pytest

from tm.flow.operations import Operation, ResponseMode
from tm.flow.policies import FlowPolicies
from tm.flow.runtime import FlowRuntime
from tm.flow.spec import FlowSpec, StepDef


class DummyFlow:
    def __init__(self, spec: FlowSpec):
        self._spec = spec

    @property
    def name(self) -> str:
        return self._spec.name

    def spec(self) -> FlowSpec:
        return self._spec


def _build_flow_spec(name: str, *, key: str | None = None) -> FlowSpec:
    spec = FlowSpec(name=name)
    spec.add_step(StepDef("start", Operation.TASK, next_steps=("router",)))
    config = {"default": "left"}
    if key is not None:
        config["key"] = key
    spec.add_step(
        StepDef(
            "router",
            Operation.SWITCH,
            next_steps=("left", "right"),
            config=config,
        )
    )
    spec.add_step(StepDef("left", Operation.TASK, next_steps=("finish",)))
    spec.add_step(StepDef("right", Operation.TASK, next_steps=("finish",)))
    spec.add_step(StepDef("finish", Operation.FINISH))
    return spec


def test_run_immediate_follows_switch_default_path():
    spec = _build_flow_spec("demo", key=None)
    flow = DummyFlow(spec)
    runtime = FlowRuntime({spec.name: flow})

    result = runtime.run("demo")

    assert result["status"] == "immediate"
    assert result["flow"] == "demo"
    assert result["result"]["steps"] == ["start", "router", "left", "finish"]


def test_run_immediate_respects_switch_key_selection():
    spec = _build_flow_spec("branch", key="right")
    flow = DummyFlow(spec)
    runtime = FlowRuntime({spec.name: flow})

    result = runtime.run("branch")

    assert result["result"]["steps"] == ["start", "router", "right", "finish"]


def test_run_deferred_requires_policy_opt_in():
    spec = FlowSpec(name="async")
    flow = DummyFlow(spec)

    deferred_runtime = FlowRuntime(
        {spec.name: flow},
        policies=FlowPolicies(response_mode=ResponseMode.DEFERRED, allow_deferred=True),
    )
    payload = {"payload": 1}

    response = deferred_runtime.run("async", inputs=payload)

    assert response["status"] == "pending"
    assert response["token"]
    assert response["flow"] == "async"

    strict_runtime = FlowRuntime(
        {spec.name: flow},
        policies=FlowPolicies(response_mode=ResponseMode.DEFERRED, allow_deferred=False),
    )

    with pytest.raises(RuntimeError):
        strict_runtime.run("async")
