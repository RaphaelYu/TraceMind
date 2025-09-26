"""Routes model operations into flow executions."""

from __future__ import annotations

from typing import Any, Dict, Mapping, MutableMapping, Optional, Protocol

try:  # pragma: no cover - optional dependency shim
    from tm.flow.operations import ResponseMode
except ModuleNotFoundError:  # pragma: no cover
    from enum import Enum

    class ResponseMode(Enum):  # type: ignore[redefinition]
        IMMEDIATE = "immediate"
        DEFERRED = "deferred"

from tm.ai.hooks import DecisionHook, NullDecisionHook
from tm.obs.recorder import Recorder
from .binding import BindingSpec, Operation, _coerce_operation


class RuntimeLike(Protocol):  # pragma: no cover - structural typing helper
    async def run(
        self,
        name: str,
        inputs: Optional[Mapping[str, Any]] = None,
        response_mode: Optional[ResponseMode] = None,
    ) -> Dict[str, Any]:
        ...


class OperationRouter:
    """Resolve operations to flows and invoke the runtime."""

    def __init__(
        self,
        runtime: RuntimeLike,
        bindings: Mapping[str, BindingSpec],
        *,
        hook: Optional[DecisionHook] = None,
    ):
        self._runtime = runtime
        self._bindings = dict(bindings)
        self._hook = hook or NullDecisionHook()

    async def dispatch(
        self,
        *,
        model: str,
        operation: Operation | str,
        payload: MutableMapping[str, object],
        context: Optional[Dict[str, object]] = None,
        response_mode: Optional[ResponseMode] = None,
    ) -> Dict[str, object]:
        spec = self._bindings.get(model)
        if spec is None:
            raise KeyError(f"No bindings registered for model '{model}'")

        op_enum = _coerce_operation(operation)
        Recorder.default().on_service_request(model, op_enum.value)
        ctx: Dict[str, object] = {"model": model, "op": op_enum, "payload": payload}
        if context:
            ctx.update(context)

        self._hook.before_route(ctx)

        flow_name = spec.resolve(op_enum, ctx)
        if flow_name is None:
            raise LookupError(f"No binding rule matched for op '{op_enum.value}' on model '{model}'")

        inputs = dict(payload)
        inputs.setdefault("model", model)
        inputs.setdefault("op", op_enum.value)
        if context:
            inputs.setdefault("context", context)

        result = await self._runtime.run(flow_name, inputs=inputs, response_mode=response_mode)
        enriched = {"flow": flow_name, **result}
        self._hook.after_result(enriched)
        return enriched
