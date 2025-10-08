import asyncio

import pytest

from tm.flow.operations import Operation, ResponseMode
from tm.flow.policies import FlowPolicies
from tm.flow.runtime import FlowRuntime
from tm.flow.spec import FlowSpec, StepDef
from tm.flow.trace_store import FlowTraceSink
from tm.storage.binlog import BinaryLogReader


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


@pytest.mark.asyncio
async def test_run_immediate_follows_switch_default_path():
    spec = _build_flow_spec("demo", key=None)
    flow = DummyFlow(spec)
    runtime = FlowRuntime({spec.name: flow})

    result = await runtime.run("demo")

    assert result["status"] == "ok"
    assert result["output"]["mode"] == "immediate"
    assert [step["name"] for step in result["output"]["steps"]] == ["start", "router", "left", "finish"]
    assert result["flow"] == "demo"
    assert result["flow_id"] == "demo"
    assert result["flow_rev"].startswith("rev-")

    await runtime.aclose()


@pytest.mark.asyncio
async def test_run_immediate_respects_switch_key_selection():
    spec = _build_flow_spec("branch", key="right")
    flow = DummyFlow(spec)
    runtime = FlowRuntime({spec.name: flow})

    result = await runtime.run("branch")

    assert [step["name"] for step in result["output"]["steps"]] == ["start", "router", "right", "finish"]
    assert result["flow_id"] == "branch"

    await runtime.aclose()


@pytest.mark.asyncio
async def test_run_deferred_requires_policy_opt_in():
    spec = FlowSpec(name="async")
    flow = DummyFlow(spec)

    deferred_runtime = FlowRuntime(
        {spec.name: flow},
        policies=FlowPolicies(response_mode=ResponseMode.DEFERRED, allow_deferred=True),
    )
    payload = {"payload": 1}

    response = await deferred_runtime.run("async", inputs=payload)

    assert response["status"] == "ok"
    assert response["output"]["status"] == "pending"
    assert response["output"]["token"]

    strict_runtime = FlowRuntime(
        {spec.name: flow},
        policies=FlowPolicies(response_mode=ResponseMode.DEFERRED, allow_deferred=False),
    )

    result = await strict_runtime.run("async")
    assert result["status"] == "error"

    await deferred_runtime.aclose()
    await strict_runtime.aclose()


@pytest.mark.asyncio
async def test_runtime_emits_trace_span(tmp_path):
    spec = FlowSpec(name="trace-demo")
    spec.add_step(StepDef("start", Operation.TASK))
    flow = DummyFlow(spec)

    trace_sink = FlowTraceSink(dir_path=str(tmp_path))
    runtime = FlowRuntime({spec.name: flow}, trace_sink=trace_sink)

    result = await runtime.run("trace-demo")
    assert result["status"] == "ok"

    await runtime.aclose()

    reader = BinaryLogReader(str(tmp_path))
    records = list(reader.scan())
    import json

    payloads = [json.loads(payload) for et, payload in records if et == "FlowTrace"]
    assert payloads, "expected at least one trace span"

    event = payloads[0]
    assert event["flow_rev"] == spec.flow_revision()
    assert event["step_id"] == spec.step_id("start")
    assert event["seq"] == 0
    assert event["status"] == "ok"
    assert event["error_code"] is None
    assert event["start_ts"] <= event["end_ts"]


@pytest.mark.asyncio
async def test_runtime_notifies_run_end_listeners():
    spec = FlowSpec(name="listener")
    spec.add_step(StepDef("start", Operation.TASK))
    flow = DummyFlow(spec)

    captured = []

    async def listener(record):
        captured.append(record)

    runtime = FlowRuntime({spec.name: flow}, run_listeners=(listener,))
    await runtime.run("listener")
    await asyncio.sleep(0)
    await runtime.aclose()

    assert len(captured) == 1
    record = captured[0]
    assert record.status == "ok"
    assert record.binding is None
    assert record.selected_flow == "listener"
