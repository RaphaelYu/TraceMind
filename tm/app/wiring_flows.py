from __future__ import annotations

import os
from typing import Dict

from fastapi import APIRouter, HTTPException

from tm.flow.runtime import FlowRuntime
from tm.flow.operations import ResponseMode
from tm.flow.trace_store import FlowTraceSink
from tm.io.http2_app import cfg
from .example_crud_flows import build_flows

router = APIRouter(prefix="/flow", tags=["flow"])

_flows = build_flows()
_trace_sink = FlowTraceSink(dir_path=os.path.join(cfg.data_dir, "trace"))
_runtime = FlowRuntime(flows=_flows, trace_sink=_trace_sink)


@router.post("/run")
def run_flow(payload: Dict[str, object]) -> Dict[str, object]:
    op = payload.get("op")
    if not isinstance(op, str):
        raise HTTPException(status_code=400, detail="Missing op")

    body = payload.get("payload")
    flow_name = f"sample.{op}"
    mode = ResponseMode.DEFERRED if op == "create" else ResponseMode.IMMEDIATE

    try:
        result = _runtime.run(flow_name, inputs=body, response_mode=mode)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if result["status"] == "deferred":
        return {"status": "accepted", "correlationId": result["token"]}

    return {"status": "ok", "result": result["result"]}
