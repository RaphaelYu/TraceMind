import pytest

from tm.service import BindingRule, BindingSpec, Operation, OperationRouter


def test_binding_spec_resolves_by_operation_and_predicate():
    def match_update(ctx):
        return ctx.get("payload", {}).get("target") == "primary"

    binding = BindingSpec(
        model="Generic",
        rules=[
            BindingRule(operation=Operation.READ, flow_name="flow-read"),
            BindingRule(operation=Operation.UPDATE, flow_name="flow-update", predicate=match_update),
        ],
    )

    ctx_read = {"op": Operation.READ, "payload": {}}
    ctx_update_ok = {"op": Operation.UPDATE, "payload": {"target": "primary"}}
    ctx_update_skip = {"op": Operation.UPDATE, "payload": {"target": "other"}}

    assert binding.resolve(Operation.READ, ctx_read) == "flow-read"
    assert binding.resolve(Operation.UPDATE, ctx_update_ok) == "flow-update"
    assert binding.resolve(Operation.UPDATE, ctx_update_skip) is None


@pytest.mark.asyncio
async def test_operation_router_dispatch_invokes_runtime_with_flow():
    calls = []

    class FakeRuntime:
        async def run(self, name, inputs=None, response_mode=None, ctx=None):  # noqa: ANN001
            calls.append((name, inputs, response_mode))
            return {
                "status": "ok",
                "run_id": "test",
                "queued_ms": 0.0,
                "exec_ms": 0.0,
                "output": {"mode": "deferred", "status": "pending", "token": "t-1"},
                "error_code": None,
                "error_message": None,
            }

    binding = BindingSpec(
        model="Generic",
        rules=[BindingRule(operation=Operation.READ, flow_name="flow-read")],
    )

    router = OperationRouter(FakeRuntime(), {"Generic": binding})
    payload = {"data": {"id": "123"}}

    result = await router.dispatch(model="Generic", operation=Operation.READ, payload=payload, context={"extra": True})

    assert calls[0][0] == "flow-read"
    assert calls[0][1]["data"] == {"id": "123"}
    assert result["flow"] == "flow-read"
    assert result["status"] == "ok"
    assert result["output"]["status"] == "pending"
