from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException

from pathlib import Path

from tm.flow.runtime import FlowRuntime
from tm.flow.operations import ResponseMode
from tm.flow.policies import FlowPolicies
from tm.flow.trace_store import FlowTraceSink
from tm.flow.artifacts import export_flow_artifact
from tm.ai.retrospect import Retrospect
from tm.ai.reward_config import load_reward_weights
from tm.ai.run_pipeline import RunEndPipeline
from tm.ai.tuner import BanditTuner
from tm.ai.policy_adapter import AsyncMcpClient, McpPolicyAdapter
from tm.io.http2_app import cfg
from .example_crud_flows import build_flows
from tm.flow.spec import FlowSpec
from tm.recipes import (
    container_health,
    mcp_tool_call,
    pod_health_check,
)

router = APIRouter(prefix="/flow", tags=["flow"])


@dataclass
class _SpecFlow:
    spec_obj: FlowSpec

    @property
    def name(self) -> str:
        return self.spec_obj.name

    def spec(self) -> FlowSpec:
        return self.spec_obj


def _load_flows() -> Dict[str, object]:
    flows: Dict[str, object] = build_flows()

    recipe_specs = [
        pod_health_check(namespace="default", label_selector="app=demo"),
        container_health(container_names=["demo"]),
        mcp_tool_call(tool="files", method="list", param_keys=["path"]),
    ]

    for spec in recipe_specs:
        flows[spec.name] = _SpecFlow(spec)

    return flows


_flows = _load_flows()
_trace_sink = FlowTraceSink(dir_path=os.path.join(cfg.data_dir, "trace"))
_retrospect = Retrospect()
_tuner = BanditTuner()
_policy_adapter: Optional[McpPolicyAdapter] = None
if cfg.policy_mcp_url:
    _policy_adapter = McpPolicyAdapter(
        _tuner,
        AsyncMcpClient(base_url=cfg.policy_mcp_url, timeout=2.0, retries=2, backoff=0.25),
    )
_reward_weights = load_reward_weights()
_run_pipeline = RunEndPipeline(
    _retrospect,
    _tuner,
    weights=_reward_weights,
    policy_adapter=_policy_adapter,
)
_runtime = FlowRuntime(
    flows=_flows,
    trace_sink=_trace_sink,
    policies=FlowPolicies(response_mode=ResponseMode.DEFERRED),
    run_listeners=(_run_pipeline.on_run_end,),
)

_artifact_dir = Path(cfg.data_dir) / "artifacts" / "flows"
for flow in _flows.values():
    try:
        spec = flow.spec()
    except Exception:
        continue
    try:
        export_flow_artifact(spec, _artifact_dir)
    except Exception:
        continue


@router.post("/run")
async def run_flow(payload: Dict[str, object]) -> Dict[str, object]:
    body = payload.get("payload")
    if body is not None and not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="payload must be an object")

    requested_flow = None
    if isinstance(body, dict):
        maybe_flow = body.get("flow")
        if isinstance(maybe_flow, str):
            requested_flow = maybe_flow

    if requested_flow is None:
        op = payload.get("op")
        if not isinstance(op, str):
            raise HTTPException(status_code=400, detail="Missing op")
        requested_flow = f"sample.{op}"

    try:
        result = await _runtime.run(requested_flow, inputs=body or {}, response_mode=ResponseMode.DEFERRED)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    status = result.get("status")
    output = result.get("output", {})

    if status == "rejected":
        raise HTTPException(status_code=429, detail=result.get("error_message", "queue full"))
    if status == "error":
        raise HTTPException(status_code=500, detail=result.get("error_message", "flow error"))

    if output.get("mode") == "deferred":
        if output.get("status") == "pending":
            return {"status": "accepted", "correlationId": output.get("token")}
        if output.get("status") == "ready":
            return {"status": "ok", "result": output.get("result")}

    return {"status": "ok", "result": output}
