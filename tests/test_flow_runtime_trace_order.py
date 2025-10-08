import asyncio
from collections import defaultdict

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


class ListTraceSink:
    def __init__(self):
        self.events = []

    def append(self, span):
        self.events.append(span)


@pytest.mark.asyncio
async def test_step_events_preserve_order():
    async def run_step(ctx, state):
        await asyncio.sleep(0.001)
        return state

    spec = FlowSpec(name="ordered")
    spec.add_step(StepDef("a", Operation.TASK, next_steps=("b",), run=run_step))
    spec.add_step(StepDef("b", Operation.TASK, next_steps=("c",), run=run_step))
    spec.add_step(StepDef("c", Operation.TASK, next_steps=(), run=run_step))

    sink = ListTraceSink()
    runtime = FlowRuntime(
        {spec.name: DummyFlow(spec)},
        max_concurrency=100,
        queue_capacity=200,
        trace_sink=sink,
    )

    total = 200

    async def run_one(i: int):
        await runtime.run("ordered", inputs={"value": i})

    await asyncio.gather(*[run_one(i) for i in range(total)])
    await runtime.aclose()

    runs = defaultdict(list)
    for event in sink.events:
        runs[event.run_id].append(event)

    sampled = list(runs.items())[:10]
    for run_id, events in sampled:
        seqs = [e.seq for e in events]
        assert seqs == sorted(seqs)
        steps = [e.step for e in events]
        assert steps == ["a", "b", "c"]
        assert len(seqs) == 3

    assert len(runs) == total
