from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict

from fastapi import APIRouter, HTTPException

from tm.flow.runtime import FlowRuntime
from tm.flow.operations import ResponseMode
from tm.flow.policies import FlowPolicies
from tm.flow.trace_store import FlowTraceSink
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
_runtime = FlowRuntime(
    flows=_flows,
    trace_sink=_trace_sink,
    policies=FlowPolicies(response_mode=ResponseMode.DEFERRED),
)


@router.post("/run")
def run_flow(payload: Dict[str, object]) -> Dict[str, object]:
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
        result = _runtime.run(requested_flow, inputs=body or {}, response_mode=ResponseMode.DEFERRED)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    status = result.get("status")
    if status == "pending":
        return {"status": "accepted", "correlationId": result["token"]}
    if status == "ready":
        return {"status": "ok", "result": result.get("result")}
    return {"status": status or "unknown", "result": result.get("result")}
