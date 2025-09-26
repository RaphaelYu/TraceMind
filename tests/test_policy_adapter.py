import logging

import pytest

from tm.ai.policy_adapter import AsyncMcpClient, BindingPolicy, McpPolicyAdapter
from tm.ai.tuner import BanditTuner
from tm.connectors.mcp import McpServer
from tm.flow.runtime import FlowRunRecord
from tm.service import BindingRule, BindingSpec, Operation
from tm.service.router import OperationRouter


@pytest.mark.asyncio
async def test_mcp_policy_adapter_updates_tuner_and_remote_version():
    state = {
        "version": "remote-1",
        "params": {"alpha": 0.8, "exploration_bonus": 0.15},
        "arms": ["flow_remote", "flow_local"],
    }
    server = McpServer()

    def handler(action: str, params):  # noqa: ANN001
        if action == "get":
            return {"version": state["version"], "params": state["params"]}
        if action == "list_arms":
            return {"arms": state["arms"], "version": state["version"]}
        if action == "update":
            state["version"] = "remote-2"
            state["params"] = {"alpha": 0.4, "exploration_bonus": 0.05}
            return {"version": state["version"], "params": state["params"]}
        raise ValueError(action)

    server.register_tool({"name": "policy", "handler": handler})

    async def transport(payload):  # noqa: ANN001
        return server.handle(payload)

    tuner = BanditTuner()
    adapter = McpPolicyAdapter(tuner, AsyncMcpClient(transport=transport))
    binding_key = "Generic:read"
    adapter.register_binding(binding_key, BindingPolicy(endpoint="mcp:policy", policy_ref="Generic"))

    decision = await adapter.prepare(binding_key, ("flow_a", "flow_b"), {}, "local-1")
    assert decision.fallback is False
    assert decision.remote_version == "remote-1"
    config = await tuner.config(binding_key)
    assert config.version == "remote-1"
    assert config.alpha == pytest.approx(0.8)
    assert decision.arms == state["arms"]

    record = FlowRunRecord(
        flow="flow_remote",
        flow_id="flow_remote",
        flow_rev="rev-1",
        run_id="run-1",
        selected_flow="flow_remote",
        binding=binding_key,
        status="ok",
        outcome="ok",
        queued_ms=0.0,
        exec_ms=10.0,
        duration_ms=10.0,
        start_ts=0.0,
        end_ts=0.01,
        cost_usd=None,
        user_rating=None,
        reward=1.0,
        meta={},
    )

    await adapter.post_run(record)
    config = await tuner.config(binding_key)
    assert config.version == "remote-2"
    assert config.alpha == pytest.approx(0.4)


@pytest.mark.asyncio
async def test_mcp_policy_adapter_falls_back_on_transport_failure():
    async def failing_transport(payload):  # noqa: ANN001
        raise RuntimeError("boom")

    tuner = BanditTuner()
    adapter = McpPolicyAdapter(tuner, AsyncMcpClient(transport=failing_transport))
    binding_key = "Generic:read"
    adapter.register_binding(binding_key, BindingPolicy(endpoint="mcp:policy", policy_ref="Generic"))

    decision = await adapter.prepare(binding_key, ("flow_a",), {}, "local-1")
    assert decision.fallback is True
    assert decision.arms == ["flow_a"]
    config = await tuner.config(binding_key)
    assert config.version == "local"

    record = FlowRunRecord(
        flow="flow_a",
        flow_id="flow_a",
        flow_rev="rev-1",
        run_id="run-1",
        selected_flow="flow_a",
        binding=binding_key,
        status="ok",
        outcome="ok",
        queued_ms=0.0,
        exec_ms=10.0,
        duration_ms=10.0,
        start_ts=0.0,
        end_ts=0.01,
        cost_usd=None,
        user_rating=None,
        reward=1.0,
        meta={},
    )

    await adapter.post_run(record)  # should not raise despite transport failure


@pytest.mark.asyncio
async def test_operation_router_logs_policy_versions(caplog):
    state = {
        "version": "remote-1",
        "params": {"alpha": 0.7, "exploration_bonus": 0.1},
        "arms": ["flow_remote"],
    }
    server = McpServer()

    def handler(action: str, params):  # noqa: ANN001
        if action == "get":
            return {"version": state["version"], "params": state["params"]}
        if action == "list_arms":
            return {"arms": state["arms"], "version": state["version"]}
        if action == "update":
            return {"version": state["version"], "params": state["params"]}
        raise ValueError(action)

    server.register_tool({"name": "policy", "handler": handler})

    async def transport(payload):  # noqa: ANN001
        return server.handle(payload)

    tuner = BanditTuner()
    adapter = McpPolicyAdapter(tuner, AsyncMcpClient(transport=transport))
    binding = BindingSpec(
        model="Generic",
        rules=[BindingRule(operation=Operation.READ, flow_name="flow_local")],
        policy_endpoint="mcp:policy",
        policy_ref="Generic",
    )

    class DummyRuntime:
        async def run(self, name, inputs=None, response_mode=None, ctx=None):  # noqa: ANN001
            return {"status": "ok", "flow": name, "run_id": "r", "queued_ms": 0.0, "exec_ms": 0.0, "output": {}, "error_code": None, "error_message": None}

    router = OperationRouter(DummyRuntime(), {"Generic": binding}, tuner=tuner, policy_adapter=adapter)

    caplog.set_level(logging.INFO)
    result = await router.dispatch(model="Generic", operation=Operation.READ, payload={}, context={})
    assert result["flow"] == "flow_remote"

    log_messages = [rec.message for rec in caplog.records if rec.levelno == logging.INFO]
    assert any("local_version=local" in msg and "remote_version=remote-1" in msg for msg in log_messages)
