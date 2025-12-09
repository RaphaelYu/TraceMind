"""FlowSpec recipes for MCP tool invocations."""

from __future__ import annotations

from typing import Dict, List, Any

from tm.connectors.mcp import McpClient
from tm.flow.correlate import CorrelationHub
from tm.flow.operations import Operation, ResponseMode
from tm.flow.spec import FlowSpec, StepDef


def mcp_tool_call(tool: str, method: str, param_keys: List[str]) -> FlowSpec:
    spec = FlowSpec(name=f"mcp.{tool}.{method}")
    spec.add_step(
        StepDef(
            "build",
            Operation.TASK,
            next_steps=("call",),
            config={
                "callable": _build_request(tool, method, param_keys),
                "response_mode": ResponseMode.DEFERRED.value,
            },
        )
    )
    spec.add_step(
        StepDef(
            "call",
            Operation.TASK,
            next_steps=("signal",),
            config={"callable": _invoke_tool},
        )
    )
    spec.add_step(
        StepDef(
            "signal",
            Operation.TASK,
            next_steps=(),
            config={"callable": _signal_ready},
        )
    )
    return spec


def _build_request(tool: str, method: str, param_keys: List[str]):
    keys = list(param_keys)

    def _inner(ctx: Dict[str, object]) -> Dict[str, object]:
        payload = {}
        inputs = ctx.get("inputs", {})
        for key in keys:
            if isinstance(inputs, dict) and key in inputs:
                payload[key] = inputs[key]
        ctx["request"] = {"tool": tool, "method": method, "params": payload}
        return ctx

    return _inner


def _invoke_tool(ctx: Dict[str, object]) -> Dict[str, object]:
    clients_val = ctx.get("clients")
    clients: Dict[str, object] = clients_val if isinstance(clients_val, dict) else {}
    client_obj = clients.get("mcp")
    if client_obj is None or not hasattr(client_obj, "call"):
        raise ValueError("MCP client missing in ctx['clients']['mcp']")
    client: McpClient | Any = client_obj
    request_cfg = ctx.get("request")
    request_map: Dict[str, object] = request_cfg if isinstance(request_cfg, dict) else {}
    tool = request_map.get("tool")
    method = request_map.get("method")
    params = request_map.get("params", {})
    if not isinstance(tool, str) or not isinstance(method, str):
        raise ValueError("tool and method must be strings in ctx['request']")
    if not isinstance(params, dict):
        raise ValueError("params must be a dict in ctx['request']")
    result = client.call(tool, method, params)
    ctx["result"] = result
    return ctx


def _signal_ready(ctx: Dict[str, object]) -> Dict[str, object]:
    correlator_val = ctx.get("correlator")
    hub: CorrelationHub | None = correlator_val if isinstance(correlator_val, CorrelationHub) else None
    if hub is None:
        raise ValueError("correlator must be provided in ctx['correlator']")
    req_id = ctx.get("req_id")
    if not isinstance(req_id, str):
        raise ValueError("req_id must be provided in ctx['req_id']")
    payload = {"status": "ready", "data": ctx.get("result")}
    hub.signal(req_id, payload)
    ctx["response"] = payload
    return ctx
