import asyncio
import pytest

from tm.ai.plan import PLAN_VERSION
from tm.ai.registry import reset_registries, tool_registry, flow_allow_registry
from tm.steps.ai_execute_plan import run as execute_plan


class StubRuntime:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    async def execute(self, flow_id, *, inputs=None, ctx=None):
        self.calls.append((flow_id, inputs, ctx))
        response = self.responses.get(flow_id, {"status": "ok", "result": {"flow": flow_id}})
        await asyncio.sleep(0)
        return response


def _plan_with_steps(steps, allow_tools=None, allow_flows=None):
    return {
        "version": PLAN_VERSION,
        "goal": "Test plan",
        "constraints": {},
        "allow": {"tools": list(allow_tools or []), "flows": list(allow_flows or [])},
        "steps": steps,
    }


@pytest.mark.asyncio
async def test_execute_plan_runs_tool_success():
    reset_registries()
    captured = {}

    def tool_action(items):
        captured["items"] = items
        return sorted(items)

    tool_registry.register("tool.sort", tool_action)
    tool_registry.allow(["tool.sort"])

    plan = _plan_with_steps(
        [
            {
                "id": "s1",
                "kind": "tool",
                "ref": "tool.sort",
                "inputs": {"items": [3, 1, 2]},
            }
        ],
        allow_tools=["tool.sort"],
    )

    result = await execute_plan({"plan": plan, "runtime": StubRuntime({})})
    assert result["status"] == "ok"
    assert result["steps"]["s1"]["result"] == [1, 2, 3]
    assert captured["items"] == [3, 1, 2]


@pytest.mark.asyncio
async def test_execute_plan_invokes_flow_runtime():
    reset_registries()
    flow_allow_registry.allow(["flow.child"])
    runtime = StubRuntime({"flow.child": {"status": "ok", "payload": 123}})

    plan = _plan_with_steps(
        [
            {
                "id": "child",
                "kind": "flow",
                "ref": "flow.child",
                "inputs": {"value": 10},
            }
        ],
        allow_flows=["flow.child"],
    )

    result = await execute_plan({"plan": plan, "runtime": runtime})
    assert result["status"] == "ok"
    assert runtime.calls[0][0] == "flow.child"


@pytest.mark.asyncio
async def test_execute_plan_retries_then_succeeds():
    reset_registries()
    attempts = {"count": 0}

    async def flaky_tool():
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise RuntimeError("fail once")
        return "done"

    tool_registry.register("tool.once", flaky_tool)
    tool_registry.allow(["tool.once"])

    plan = _plan_with_steps(
        [
            {
                "id": "s1",
                "kind": "tool",
                "ref": "tool.once",
                "inputs": {},
                "on_error": {"retry": {"max": 1, "backoff_ms": 0}},
            }
        ],
        allow_tools=["tool.once"],
    )

    result = await execute_plan({"plan": plan, "runtime": StubRuntime({})})
    assert result["status"] == "ok"
    assert attempts["count"] == 2


@pytest.mark.asyncio
async def test_execute_plan_fallback():
    reset_registries()

    def primary():
        raise RuntimeError("boom")

    def fallback():
        return "fallback"

    tool_registry.register("tool.primary", primary)
    tool_registry.register("tool.fallback", fallback)
    tool_registry.allow(["tool.primary", "tool.fallback"])

    plan = _plan_with_steps(
        [
            {
                "id": "s1",
                "kind": "tool",
                "ref": "tool.primary",
                "inputs": {},
                "on_error": {
                    "retry": {"max": 0},
                    "fallback": "tool.fallback",
                },
            }
        ],
        allow_tools=["tool.primary", "tool.fallback"],
    )

    result = await execute_plan({"plan": plan, "runtime": StubRuntime({})})
    assert result["status"] == "ok"
    assert result["steps"]["s1"]["result"] == "fallback"


@pytest.mark.asyncio
async def test_execute_plan_blocks_disallowed_tool():
    reset_registries()
    tool_registry.register("tool.hidden", lambda: None)

    plan = _plan_with_steps(
        [
            {
                "id": "s1",
                "kind": "tool",
                "ref": "tool.hidden",
                "inputs": {},
            }
        ],
        allow_tools=["tool.hidden"],
    )

    # Not allow-listing in registry should trigger POLICY_FORBIDDEN
    result = await execute_plan({"plan": plan, "runtime": StubRuntime({})})
    assert result["status"] == "error"
    assert result["error_code"] == "POLICY_FORBIDDEN"
