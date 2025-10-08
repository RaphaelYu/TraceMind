from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional

from tm.ai.llm_client import make_client
from tm.ai.providers.base import LlmError
from tm.ai.reflect import Reflection, ReflectionValidationError, validate_reflection
from tm.obs.recorder import Recorder

STEP_NAME = "ai.reflect"


@dataclass
class _ReflectRequest:
    provider: str
    model: str
    recent_outcomes: Mapping[str, Any]
    last_error: Optional[str]
    retrospect_stats: Mapping[str, Any]
    plan: Optional[Mapping[str, Any]]
    retries: int
    retry_backoff_ms: int
    timeout_ms: Optional[int]
    temperature: Optional[float]
    top_p: Optional[float]

    def build_prompt(self) -> str:
        payload = {
            "recent_outcomes": self.recent_outcomes,
            "last_error": self.last_error,
            "retrospect": self.retrospect_stats,
            "plan": self.plan,
        }
        instructions = (
            "You are TraceMind Reflector. Return STRICT JSON matching:\n"
            "{\n"
            '  "version": "reflect.v1",\n'
            '  "summary": string,\n'
            '  "issues": [strings],\n'
            '  "guidance": string?,\n'
            '  "plan_patch": {"ops": [{"op": "add|replace|remove", "path": "/steps/<idx>/inputs...", "value": any}] }?,\n'
            '  "policy_update": object\n'
            "}\n"
            "Never include commentary or explanations."
        )
        context = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        return instructions + "\nContext:\n" + context


def _parse_request(params: Mapping[str, Any]) -> _ReflectRequest:
    provider = str(params.get("provider", "")).strip()
    if not provider:
        raise ValueError("provider is required")

    model = str(params.get("model", "")).strip()
    if not model:
        raise ValueError("model is required")

    recent_outcomes = params.get("recent_outcomes") or {}
    if not isinstance(recent_outcomes, Mapping):
        raise ValueError("recent_outcomes must be an object")

    retros = params.get("retrospect_stats") or {}
    if not isinstance(retros, Mapping):
        raise ValueError("retrospect_stats must be an object")

    last_error = params.get("last_error")
    if last_error is not None and not isinstance(last_error, str):
        last_error = str(last_error)

    plan = params.get("plan")
    if plan is not None and not isinstance(plan, Mapping):
        raise ValueError("plan must be an object when provided")

    retries = params.get("retries", 0)
    if not isinstance(retries, int) or retries < 0:
        raise ValueError("retries must be a non-negative integer")

    retry_backoff_ms = params.get("retry_backoff_ms", 500)
    if not isinstance(retry_backoff_ms, int) or retry_backoff_ms < 0:
        raise ValueError("retry_backoff_ms must be a non-negative integer")

    timeout_ms = params.get("timeout_ms")
    if timeout_ms is not None and (not isinstance(timeout_ms, int) or timeout_ms < 0):
        raise ValueError("timeout_ms must be a non-negative integer")

    temperature = params.get("temperature")
    if temperature is not None:
        temperature = float(temperature)

    top_p = params.get("top_p")
    if top_p is not None:
        top_p = float(top_p)

    return _ReflectRequest(
        provider=provider,
        model=model,
        recent_outcomes=dict(recent_outcomes),
        last_error=last_error,
        retrospect_stats=dict(retros),
        plan=dict(plan) if plan is not None else None,
        retries=retries,
        retry_backoff_ms=retry_backoff_ms,
        timeout_ms=timeout_ms,
        temperature=temperature,
        top_p=top_p,
    )


def _is_retryable_error(exc: Exception) -> bool:
    code = getattr(exc, "code", None)
    return code in {"RATE_LIMIT", "PROVIDER_ERROR", "RUN_TIMEOUT"}


async def run(
    params: Dict[str, Any], *, flow_id: Optional[str] = None, step_id: Optional[str] = None
) -> Dict[str, Any]:
    try:
        request = _parse_request(params)
    except ValueError as exc:
        return {"status": "error", "error_code": "BAD_REQUEST", "reason": str(exc)}

    client = make_client(request.provider)
    prompt = request.build_prompt()
    recorder = Recorder.default()

    attempts = request.retries + 1
    retries_done = 0
    reflection: Optional[Reflection] = None
    error_code = "GUARD_BLOCKED"
    error_reason = "invalid response"
    overall_start = time.perf_counter()

    for attempt in range(1, attempts + 1):
        try:
            result = await client.call(
                model=request.model,
                prompt=prompt,
                temperature=request.temperature,
                top_p=request.top_p,
                timeout_ms=request.timeout_ms,
                max_retries=0,
            )
        except LlmError as exc:
            error_code = exc.code
            error_reason = exc.message
            if attempt < attempts and _is_retryable_error(exc):
                retries_done += 1
                await asyncio.sleep(request.retry_backoff_ms / 1000.0)
                continue
            duration_ms = (time.perf_counter() - overall_start) * 1000.0
            recorder.on_reflect_result(
                provider=request.provider,
                model=request.model,
                duration_ms=duration_ms,
                status="error",
            )
            return {"status": "error", "error_code": error_code, "reason": error_reason}
        except Exception as exc:  # pragma: no cover - defensive
            error_code = "PROVIDER_ERROR"
            error_reason = str(exc)
            break

        text = result.output_text.strip()
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            error_code = "GUARD_BLOCKED"
            error_reason = "reflection output was not valid JSON"
            if attempt < attempts:
                retries_done += 1
                await asyncio.sleep(request.retry_backoff_ms / 1000.0)
                continue
            break

        try:
            reflection = validate_reflection(payload)
        except ReflectionValidationError as exc:
            error_code = "GUARD_BLOCKED"
            error_reason = str(exc)
            if attempt < attempts:
                retries_done += 1
                await asyncio.sleep(request.retry_backoff_ms / 1000.0)
                continue
            break

        usage = result.usage
        duration_ms = (time.perf_counter() - overall_start) * 1000.0
        recorder.on_reflect_result(
            provider=request.provider,
            model=request.model,
            duration_ms=duration_ms,
            status="ok",
        )
        return {
            "status": "ok",
            "reflection": reflection.as_dict(),
            "reflection_json": json.dumps(reflection.as_dict(), ensure_ascii=False, separators=(",", ":")),
            "retries": retries_done,
            "usage": {
                "prompt_tokens": getattr(usage, "prompt_tokens", 0),
                "completion_tokens": getattr(usage, "completion_tokens", 0),
                "total_tokens": getattr(usage, "total_tokens", 0),
                "cost_usd": getattr(usage, "cost_usd", None),
            },
        }

    duration_ms = (time.perf_counter() - overall_start) * 1000.0
    recorder.on_reflect_result(
        provider=request.provider,
        model=request.model,
        duration_ms=duration_ms,
        status="error",
    )
    return {"status": "error", "error_code": error_code, "reason": error_reason}


try:  # pragma: no cover
    from tm.steps.registry import register_step  # type: ignore

    register_step(STEP_NAME, run)
except Exception:
    pass
