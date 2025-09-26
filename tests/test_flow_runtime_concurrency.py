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
async def test_runtime_concurrency_and_backpressure():
    start_order: list[int] = []
    active = 0

    async def run(ctx, state):
        nonlocal active
        idx = state["index"]
        start_order.append(idx)
        active += 1
        await asyncio.sleep(0.01)
        active -= 1
        return state

    spec = FlowSpec(name="slow")
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
        max_concurrency=100,
        queue_capacity=300,
        idempotency_ttl_sec=0,
    )

    total = 2000

    results = await asyncio.gather(
        *[runtime.run("slow", inputs={"index": i}) for i in range(total)]
    )

    await runtime.aclose()

    successes = [r for r in results if r["status"] == "ok"]
    rejections = [r for r in results if r["status"] == "rejected"]

    assert len(successes) + len(rejections) == total
    assert any(r["error_code"] == "QUEUE_FULL" for r in rejections)
    assert len(rejections) > 0
    assert len(successes) <= 100 + 300

    stats = runtime.get_stats()
    assert stats["active_peak"] <= 100
    assert stats["queue_depth_peak"] <= 300
    assert stats["rejected_reason"]["QUEUE_FULL"] == len(rejections)

    # FIFO start order for accepted requests
    assert start_order == sorted(start_order)
    assert len(start_order) == len(successes)
    if len(start_order) >= 10:
        assert start_order[:10] == list(range(10))
        tail_expected = list(range(len(start_order) - 10, len(start_order)))
        assert start_order[-10:] == tail_expected

    # Ensure latencies collected
    assert stats["exec_ms_p50"] >= 0
