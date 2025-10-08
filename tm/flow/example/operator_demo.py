from __future__ import annotations
from typing import Dict, Any
from ..registry import registry


@registry.operator("core.validate_payload")
def op_validate_payload(ctx, call_in: Dict[str, Any]) -> Dict[str, Any]:
    payload = call_in["inputs"].get("payload", {})
    if not isinstance(payload, dict):
        raise ValueError("payload must be a dict")
    return {"ok": bool(payload), "fields": list(payload.keys())}


registry.set_meta("core.validate_payload", reads=["inputs.payload"], writes=["vars.validate"], externals=[], pure=True)


@registry.operator("adapters.echo.annotate")
def op_echo_annotate(ctx, call_in: Dict[str, Any]) -> Dict[str, Any]:
    payload = call_in["inputs"].get("payload", {})
    validated = call_in["vars"].get("validate", {})
    return {"payload": payload, "validated": validated, "trace": ctx.trace_id}


registry.set_meta(
    "adapters.echo.annotate",
    reads=["inputs.payload", "vars.validate"],
    writes=["vars.annotate"],
    externals=[],
    pure=True,
)


@registry.operator("parallel.add_one")
def op_add_one(ctx, call_in: Dict[str, Any]) -> Dict[str, Any]:
    x = call_in["inputs"].get("x", 0)
    return {"x_plus_one": x + 1}


registry.set_meta("parallel.add_one", reads=["inputs.x"], writes=["vars.fanout.add_one"], externals=[], pure=True)


@registry.operator("parallel.square")
def op_square(ctx, call_in: Dict[str, Any]) -> Dict[str, Any]:
    x = call_in["inputs"].get("x", 0)
    return {"x_square": x * x}


registry.set_meta("parallel.square", reads=["inputs.x"], writes=["vars.fanout.square"], externals=[], pure=True)
