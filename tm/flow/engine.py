from __future__ import annotations
import time
from typing import Any, Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
from dataclasses import dataclass

from .graph import FlowGraph, NodeKind
from .registry import registry, checks
from .policies import parse_policies_from_cfg, StepPolicies


@dataclass
class ExecContext:
    """Execution context passed to operators and checks."""

    flow_name: str
    trace_id: str
    vars: Dict[str, Any]


@dataclass
class StepResult:
    """Result summary for a single step."""

    status: str  # "ok" | "error"
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    duration_ms: float = 0.0


class Engine:
    """Synchronous engine with SWITCH/PARALLEL, before/after checks, retry/timeout, and Airflow-style tracing."""

    def __init__(self, tracer: Optional[Any] = None):
        from .tracer import AirflowStyleTracer

        self.tracer = tracer or AirflowStyleTracer()

    # --------------- internal helpers ---------------
    @staticmethod
    def _get_path(root: Dict[str, Any], dotted: str) -> Any:
        """Very small JSONPath-lite: $.vars.*, $.inputs.*, $.cfg.*"""
        if not dotted or not dotted.startswith("$"):
            return dotted
        cur = {"vars": root.get("vars", {}), "inputs": root.get("inputs", {}), "cfg": root.get("cfg", {})}
        parts = dotted.lstrip("$").lstrip(".").split(".")
        cur = cur.get(parts[0], {}) if parts else {}
        for p in parts[1:]:
            if isinstance(cur, dict):
                cur = cur.get(p)
            else:
                cur = None
                break
        return cur

    def _run_checks(self, names: List[str] | None, ctx: ExecContext, call_in: Dict[str, Any]):
        if not names:
            return
        for name in names:
            checks.get(name)(ctx, call_in)

    def _run_operator(
        self, op_name: str, ctx: ExecContext, call_in: Dict[str, Any], pol: StepPolicies
    ) -> Dict[str, Any]:
        attempts = 0
        last_exc: Optional[Exception] = None
        while attempts < pol.retry.max_attempts:
            attempts += 1
            try:
                if pol.timeout.timeout_ms:
                    with ThreadPoolExecutor(max_workers=1) as ex:
                        fut = ex.submit(registry.get(op_name), ctx, call_in)
                        return fut.result(timeout=pol.timeout.timeout_ms / 1000.0)
                else:
                    return registry.get(op_name)(ctx, call_in)
            except TimeoutError as e:
                last_exc = e
            except Exception as e:
                last_exc = e
            if attempts < pol.retry.max_attempts and pol.retry.backoff_ms > 0:
                time.sleep(pol.retry.backoff_ms / 1000.0)
        raise last_exc if last_exc else RuntimeError("operator failed without exception?")

    # --------------- public API ---------------
    def run(self, flow: FlowGraph, *, inputs: Dict[str, Any] | None = None) -> Tuple[str, Dict[str, Any]]:
        run_id = self.tracer.begin(flow.name)
        ctx = ExecContext(flow_name=flow.name, trace_id=run_id, vars={})
        inputs = inputs or {}

        # record edges for later visualization
        try:
            self.tracer.record_edges(run_id, list(flow.to_networkx().edges()))
        except Exception:
            pass

        current = flow.entry()
        while True:
            step = flow.node(current)
            t0 = time.time()

            if step.kind is NodeKind.TASK:
                call_in = {"inputs": inputs, "cfg": step.cfg, "vars": ctx.vars}
                pol = parse_policies_from_cfg(step.cfg)
                try:
                    self._run_checks(step.cfg.get("before"), ctx, call_in)
                    out = self._run_operator(step.uses, ctx, call_in, pol)
                    self._run_checks(step.cfg.get("after"), ctx, {"**out": out, **call_in})
                    res = StepResult(status="ok", output=out, duration_ms=(time.time() - t0) * 1000)
                    ctx.vars[step.id] = out
                except Exception as e:
                    res = StepResult(status="error", error=str(e), duration_ms=(time.time() - t0) * 1000)
                self.tracer.on_step(run_id, step, res, call_in)
                if res.status != "ok":
                    self.tracer.end(run_id, "error")
                    break

            elif step.kind is NodeKind.SWITCH:
                root = {"vars": ctx.vars, "inputs": inputs, "cfg": step.cfg}
                key = self._get_path(root, step.cfg.get("key_from"))
                chosen = None
                for succ in flow.successors(current):
                    casev = flow.edge_attr(current, succ, "case", None)
                    if casev == key:
                        chosen = succ
                        break
                if chosen is None:
                    for succ in flow.successors(current):
                        if flow.edge_attr(current, succ, "case", None) == step.cfg.get("default", "_DEFAULT"):
                            chosen = succ
                            break
                res = StepResult(
                    status="ok",
                    output={"key": key, "chosen_case": (key if chosen else step.cfg.get("default"))},
                    duration_ms=(time.time() - t0) * 1000,
                )
                self.tracer.on_step(run_id, step, res, {"key_from": step.cfg.get("key_from")})
                if chosen is None:
                    self.tracer.end(run_id, "error")
                    break
                current = chosen
                continue

            elif step.kind is NodeKind.PARALLEL:
                uses = list(step.cfg.get("uses", []))
                max_workers = int(step.cfg.get("max_workers", 4))
                call_in_base = {"inputs": inputs, "cfg": step.cfg, "vars": ctx.vars}
                pol = parse_policies_from_cfg(step.cfg)
                outputs: Dict[str, Any] = {}
                try:

                    def _one(op_name: str):
                        self._run_checks(step.cfg.get("before"), ctx, call_in_base)
                        out = self._run_operator(op_name, ctx, call_in_base, pol)
                        self._run_checks(step.cfg.get("after"), ctx, {"**out": out, **call_in_base})
                        return op_name, out

                    with ThreadPoolExecutor(max_workers=max_workers) as ex:
                        futs = {ex.submit(_one, u): u for u in uses}
                        for fut in as_completed(futs):
                            name, out = fut.result()
                            outputs[name] = out
                    res = StepResult(status="ok", output={"parallel": outputs}, duration_ms=(time.time() - t0) * 1000)
                    ctx.vars[step.id] = outputs
                except Exception as e:
                    res = StepResult(status="error", error=str(e), duration_ms=(time.time() - t0) * 1000)
                self.tracer.on_step(run_id, step, res, call_in_base)
                if res.status != "ok":
                    self.tracer.end(run_id, "error")
                    break

            elif step.kind is NodeKind.FINISH:
                self.tracer.on_step(run_id, step, StepResult(status="ok", duration_ms=(time.time() - t0) * 1000), {})
                self.tracer.end(run_id, "ok")
                break

            # single-successor semantics (except SWITCH which already set `current`)
            succ = flow.successors(current)
            if not succ:
                self.tracer.end(run_id, "ok")
                break
            current = succ[0]

        return run_id, ctx.vars
