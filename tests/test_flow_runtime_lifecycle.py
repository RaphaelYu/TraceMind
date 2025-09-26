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
@pytest.mark.parametrize(
    "async_before, async_run, async_after",
    [
        (False, False, False),
        (True, False, True),
        (False, True, True),
    ],
)
async def test_lifecycle_hooks_execute_in_order(async_before, async_run, async_after):
    events = []

    def make_before():
        if async_before:
            async def before(ctx):
                events.append(("before", ctx["step"]))
            return before

        def before(ctx):
            events.append(("before", ctx["step"]))
        return before

    def make_run():
        if async_run:
            async def run(ctx, payload):
                events.append(("run", ctx["step"]))
                return {"value": payload.get("value", 0) + 1}
            return run

        def run(ctx, payload):
            events.append(("run", ctx["step"]))
            return {"value": payload.get("value", 0) + 1}
        return run

    def make_after():
        if async_after:
            async def after(ctx, output):
                events.append(("after", ctx["step"], output["value"]))
            return after

        def after(ctx, output):
            events.append(("after", ctx["step"], output["value"]))
        return after

    spec = FlowSpec(name="hooked")
    spec.add_step(
        StepDef(
            name="start",
            operation=Operation.TASK,
            next_steps=("finish",),
            before=make_before(),
            run=make_run(),
            after=make_after(),
        )
    )
    spec.add_step(StepDef(name="finish", operation=Operation.FINISH))

    runtime = FlowRuntime({spec.name: DummyFlow(spec)})
    result = await runtime.run("hooked", inputs={"value": 1})

    assert result["status"] == "ok"
    assert events[0][0] == "before"
    assert events[1][0] == "run"
    assert events[2][0] == "after"
    assert result["output"]["state"]["value"] == 2

    await runtime.aclose()


@pytest.mark.asyncio
async def test_lifecycle_on_error_invoked_and_after_skipped():
    events = []

    async def run(ctx, payload):
        events.append("run")
        raise RuntimeError("boom")

    async def on_error(ctx, exc):
        events.append(("error", ctx["step"], str(exc)))

    async def after(ctx, output):  # pragma: no cover - should not run
        events.append("after")

    spec = FlowSpec(name="error-flow")
    spec.add_step(
        StepDef(
            name="start",
            operation=Operation.TASK,
            next_steps=(),
            run=run,
            after=after,
            on_error=on_error,
        )
    )

    runtime = FlowRuntime({spec.name: DummyFlow(spec)})

    result = await runtime.run("error-flow", inputs={})

    assert result["status"] == "error"
    assert result["error_message"] == "boom"
    assert events == ["run", ("error", "start", "boom")]

    await runtime.aclose()
