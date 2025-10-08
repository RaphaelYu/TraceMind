from __future__ import annotations

import asyncio
import json

import uuid
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional

from tm.ai.plan import Plan, PlanStep, validate_plan
from tm.ai.registry import PolicyForbiddenError, flow_allow_registry, tool_registry
from tm.flow.runtime import FlowRuntime
from tm.obs.recorder import Recorder
from tm.utils.async_tools import default_backoff

STEP_NAME = "ai.execute_plan"


@dataclass
class StepContext:
    step: PlanStep
    attempt: int = 0
    fallback_executed: bool = False


async def run(
    params: Dict[str, Any],
    *,
    flow_id: Optional[str] = None,
    step_id: Optional[str] = None,
    runtime: Optional[FlowRuntime] = None,
) -> Dict[str, Any]:
    runtime_obj = runtime or params.get("runtime")
    if runtime_obj is None:
        raise RuntimeError("ai.execute_plan requires a FlowRuntime instance")
    if not hasattr(runtime_obj, "execute"):
        raise TypeError("runtime must expose an 'execute' coroutine")

    plan_payload = params.get("plan") or params.get("plan_ref")
    if isinstance(plan_payload, str):
        try:
            plan_payload = json.loads(plan_payload)
        except json.JSONDecodeError as exc:
            return {"status": "error", "error_code": "BAD_PLAN", "reason": f"Plan JSON invalid: {exc}"}

    if not isinstance(plan_payload, Mapping):
        return {"status": "error", "error_code": "BAD_PLAN", "reason": "plan must be a JSON object"}

    try:
        plan = validate_plan(plan_payload)
    except Exception as exc:
        return {"status": "error", "error_code": "BAD_PLAN", "reason": str(exc)}

    plan_store: Dict[str, Dict[str, Any]] = {}
    parent_span = params.get("span_id") or uuid.uuid4().hex
    results: Dict[str, Any] = {}
    recorder = Recorder.default()

    for plan_step in plan.steps:
        try:
            _require_allow(plan_step)
        except PolicyForbiddenError as exc:
            return {"status": "error", "error_code": exc.error_code, "reason": str(exc)}

        step_ctx = StepContext(step=plan_step)
        outcome = await _execute_step(
            step_ctx,
            plan=plan,
            runtime=runtime_obj,
            plan_results=plan_store,
            parent_span=parent_span,
            recorder=recorder,
        )
        results[plan_step.id] = outcome
        if outcome.get("status") != "ok" and params.get("stop_on_error", True):
            return {
                "status": "error",
                "error_code": outcome.get("error_code", "STEP_FAILED"),
                "reason": outcome.get("reason", "step failed"),
                "plan": plan.as_dict(),
                "steps": results,
            }

    return {
        "status": "ok",
        "plan": plan.as_dict(),
        "steps": results,
    }


def _require_allow(step: PlanStep) -> None:
    if step.kind == "tool":
        tool_registry.require_allowed(step.ref, reason="execute_plan")
    elif step.kind == "flow":
        flow_allow_registry.require_allowed(step.ref, reason="execute_plan")


async def _execute_step(
    context: StepContext,
    *,
    plan: Plan,
    runtime: FlowRuntime,
    plan_results: Dict[str, Dict[str, Any]],
    parent_span: str,
    recorder: Recorder,
) -> Dict[str, Any]:
    step = context.step
    retry_policy = step.on_error.retry if step.on_error else None
    max_attempts = (retry_policy.max + 1) if retry_policy else 1
    backoff_ms = retry_policy.backoff_ms if retry_policy else None

    attempt = 0
    error: Optional[Exception] = None

    while attempt < max_attempts:
        attempt += 1
        context.attempt = attempt
        try:
            result = await _dispatch_step(
                step,
                plan=plan,
                runtime=runtime,
                plan_results=plan_results,
                parent_span=parent_span,
            )
        except PolicyForbiddenError as exc:
            return {"status": "error", "error_code": exc.error_code, "reason": str(exc)}
        except Exception as exc:
            error = exc
            if attempt >= max_attempts:
                break
            await asyncio.sleep((backoff_ms or int(default_backoff(attempt) * 1000)) / 1000.0)
            continue

        if result.get("status") == "ok":
            plan_results[step.id] = result
            return result
        else:
            error = RuntimeError(result.get("reason", "step failed"))
            if attempt >= max_attempts:
                break
            await asyncio.sleep((backoff_ms or int(default_backoff(attempt) * 1000)) / 1000.0)

    fallback_ref = step.on_error.fallback if step.on_error else None
    if fallback_ref:
        try:
            _require_allow(PlanStep(id=step.id, kind=step.kind, ref=fallback_ref, inputs=step.inputs))
        except PolicyForbiddenError as exc:
            return {"status": "error", "error_code": exc.error_code, "reason": str(exc)}
        context.fallback_executed = True
        return await _dispatch_step(
            PlanStep(id=step.id, kind=step.kind, ref=fallback_ref, inputs=step.inputs, on_error=None),
            plan=plan,
            runtime=runtime,
            plan_results=plan_results,
            parent_span=parent_span,
        )

    reason = str(error) if error else "step failed"
    return {"status": "error", "error_code": "STEP_FAILED", "reason": reason}


async def _dispatch_step(
    step: PlanStep,
    *,
    plan: Plan,
    runtime: FlowRuntime,
    plan_results: Dict[str, Dict[str, Any]],
    parent_span: str,
) -> Dict[str, Any]:
    inputs = _resolve_inputs(step.inputs, plan_results)

    if step.kind == "tool":
        tool_entry = tool_registry.get(step.ref)
        handler = tool_entry.handler
        result = handler(**inputs)
        if asyncio.iscoroutine(result):  # pragma: no cover - handler may be async
            result = await result
        return {"status": "ok", "result": result}

    if step.kind == "flow":
        span_id = uuid.uuid4().hex
        child_ctx = {
            "parent_span_id": parent_span,
            "span_id": span_id,
            "plan_step": step.id,
        }
        output = await runtime.execute(step.ref, inputs=inputs, ctx=child_ctx)
        return {"status": output.get("status", "ok"), "result": output}

    raise RuntimeError(f"Unsupported step kind: {step.kind}")


def _resolve_inputs(raw_inputs: Mapping[str, Any], plan_results: Mapping[str, Dict[str, Any]]) -> Dict[str, Any]:
    resolved: Dict[str, Any] = {}
    for key, value in raw_inputs.items():
        if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
            ref = value[2:-1]
            step_id, _, attr = ref.partition(".")
            if not attr:
                attr = "result"
            source = plan_results.get(step_id, {})
            resolved[key] = source.get(attr)
        else:
            resolved[key] = value
    return resolved


try:  # pragma: no cover
    from tm.steps.registry import register_step  # type: ignore

    register_step(STEP_NAME, run)
except Exception:
    pass
