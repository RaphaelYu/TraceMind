from __future__ import annotations

import time
from typing import Any, Dict, Mapping, Optional, Set

from .correlate import CorrelationHub
from .flow import Flow
from .operations import Operation, ResponseMode
from .policies import FlowPolicies
from .spec import FlowSpec, StepDef
from .trace_store import FlowTraceSink, TraceSpanLike
from tm.obs.recorder import Recorder


class FlowRuntime:
    """Minimal runtime that selects flows and mediates execution mode."""

    def __init__(
        self,
        flows: Mapping[str, Flow] | None = None,
        *,
        policies: FlowPolicies | None = None,
        correlator: CorrelationHub | None = None,
        trace_sink: FlowTraceSink | None = None,
    ) -> None:
        self._flows: Dict[str, Flow] = dict(flows or {})
        self._policies = policies or FlowPolicies()
        self._correlator = correlator or CorrelationHub()
        self._trace_sink = trace_sink
        self._recorder = Recorder.default()
        self._pending_tokens: Set[str] = set()

    def register(self, flow: Flow) -> None:
        self._flows[flow.name] = flow

    def choose_flow(self, name: str) -> Flow:
        try:
            return self._flows[name]
        except KeyError as exc:  # pragma: no cover - defensive guard
            raise KeyError(f"Unknown flow: {name}") from exc

    def build_dag(self, flow: Flow) -> FlowSpec:
        return flow.spec()

    def run(
        self,
        name: str,
        *,
        inputs: Optional[Dict[str, Any]] = None,
        response_mode: Optional[ResponseMode] = None,
    ) -> Dict[str, Any]:
        flow = self.choose_flow(name)
        spec = self.build_dag(flow)
        mode = response_mode or self._policies.response_mode
        model_name = None
        if isinstance(inputs, dict):
            maybe = inputs.get("model")
            if isinstance(maybe, str):
                model_name = maybe

        if mode is ResponseMode.DEFERRED:
            if not self._policies.allow_deferred:
                raise RuntimeError("Deferred execution is disabled by policy")
            payload = dict(inputs or {})
            token = self._correlator.reserve(spec.name, payload)
            req_id = payload.get("req_id")
            ready: Optional[Dict[str, Any]] = None
            self._recorder.on_flow_started(spec.name, model_name)
            pending_key = req_id if isinstance(req_id, str) else token
            if isinstance(req_id, str):
                ready = self._correlator.consume_signal(req_id)
                wait_s = max(float(getattr(self._policies, "short_wait_s", 0.0)), 0.0)
                if ready is None and wait_s > 0:
                    deadline = time.time() + wait_s
                    while ready is None and time.time() < deadline:
                        time.sleep(min(0.005, deadline - time.time()))
                        ready = self._correlator.consume_signal(req_id)
            if ready is not None:
                self._correlator.consume(token)
                if pending_key and pending_key in self._pending_tokens:
                    self._pending_tokens.discard(pending_key)
                    self._recorder.on_flow_pending(-1)
                self._recorder.on_flow_finished(spec.name, model_name, "ok")
                return {
                    "status": "ready",
                    "token": token,
                    "flow": spec.name,
                    "result": ready,
                }
            if pending_key:
                self._pending_tokens.add(pending_key)
                self._recorder.on_flow_pending(+1)
            return {"status": "pending", "token": token, "flow": spec.name}

        self._recorder.on_flow_started(spec.name, model_name)
        result = self._execute_immediately(spec, inputs)
        self._recorder.on_flow_finished(spec.name, model_name, "ok")
        return {"status": "immediate", "flow": spec.name, "result": result}

    def _execute_immediately(
        self,
        spec: FlowSpec,
        inputs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Walk the DAG linearly while emitting trace spans."""

        executed: list[str] = []
        current = spec.entrypoint or (next(iter(spec.steps)) if spec.steps else None)
        visited = set()

        while current:
            step_def = spec.step(current)
            t0 = time.time()
            error: Optional[str] = None
            next_step: Optional[str] = None
            try:
                next_step = self._next_step(step_def, inputs)
            except Exception as exc:  # pragma: no cover - defensive guard
                error = str(exc)
            t1 = time.time()

            executed.append(current)
            visited.add(current)

            if self._trace_sink is not None:
                span = TraceSpanLike(
                    flow=spec.name,
                    rule=spec.name,
                    step=current,
                    t0=t0,
                    t1=t1,
                    error=error,
                )
                self._trace_sink.append(span)

            if error:
                break

            if not next_step or next_step in visited:
                break
            current = next_step

        return {"inputs": dict(inputs or {}), "steps": executed}

    def _next_step(self, step: StepDef, inputs: Optional[Dict[str, Any]]) -> Optional[str]:  # noqa: ARG002
        if not step.next_steps:
            return None
        if step.operation is Operation.SWITCH:
            cfg = dict(step.config) if hasattr(step.config, "items") else {}
            key = cfg.get("key")
            if isinstance(key, str) and key in step.next_steps:
                return key
            default = cfg.get("default")
            if isinstance(default, str) and default in step.next_steps:
                return default
        return step.next_steps[0]
