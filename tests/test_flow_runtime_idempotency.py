import asyncio

import pytest

from tm.flow.operations import Operation
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


@pytest.mark.asyncio
async def test_idempotency_inflight_and_cache():
    executions = []

    async def run(ctx, state):
        executions.append(state["value"])
        await asyncio.sleep(0.01)
        return {"value": state["value"] + 1}

    spec = FlowSpec(name="idem")
    spec.add_step(
        StepDef(
            name="start",
            operation=Operation.TASK,
            next_steps=(),
            run=run,
        )
    )

    runtime = FlowRuntime(
        {spec.name: DummyFlow(spec)},
        max_concurrency=10,
        queue_capacity=20,
        idempotency_ttl_sec=0.1,
        idempotency_cache_size=4,
    )

    key = "demo-1"
    tasks = [runtime.run("idem", inputs={"value": 1}, ctx={"idempotency_key": key}) for _ in range(100)]
    results = await asyncio.gather(*tasks)

    assert len(executions) == 1
    for res in results:
        assert res["status"] == "ok"
        assert res["output"]["state"]["value"] == 2

    await asyncio.sleep(0.2)  # TTL expires

    await runtime.run("idem", inputs={"value": 1}, ctx={"idempotency_key": key})
    assert len(executions) == 2

    # Different key executes independently
    await runtime.run("idem", inputs={"value": 5}, ctx={"idempotency_key": "other"})
    assert len(executions) == 3

    await runtime.aclose()
