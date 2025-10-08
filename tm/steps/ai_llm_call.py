from __future__ import annotations
from typing import Any, Optional

from tm.ai.llm_client import make_client
from tm.ai.providers.base import LlmError
from tm.ai.recorder_bridge import record_llm_usage
from tm.utils.templating import render_template

STEP_NAME = "ai.llm_call"


async def run(params: dict[str, Any], *, flow_id: Optional[str] = None, step_id: Optional[str] = None) -> dict:
    """Execute the ai.llm_call step.

    Expected params:
      provider: str
      model: str
      template: str | None
      prompt: str | None
      vars: dict | None
      timeout_ms: int | None
      max_retries: int | None
      temperature: float | None
      top_p: float | None
    """
    provider = str(params.get("provider", "")).strip()
    model = str(params.get("model", "")).strip()
    template = params.get("template")
    prompt = params.get("prompt")
    vars_ = params.get("vars") or {}

    if not provider or not model:
        return {"status": "error", "code": "BAD_REQUEST", "reason": "provider/model required"}

    if template is None and prompt is None:
        return {"status": "error", "code": "BAD_REQUEST", "reason": "either template or prompt is required"}

    try:
        if template is not None:
            if not isinstance(vars_, dict):
                return {"status": "error", "code": "BAD_REQUEST", "reason": "vars must be a dict when template is used"}
            prompt = render_template(str(template), vars_)
        assert prompt is not None
    except KeyError as ke:
        return {"status": "error", "code": "BAD_REQUEST", "reason": str(ke)}

    client = make_client(provider)

    try:
        result = await client.call(
            model=model,
            prompt=prompt,
            temperature=params.get("temperature"),
            top_p=params.get("top_p"),
            timeout_ms=params.get("timeout_ms"),
            max_retries=int(params.get("max_retries") or 0),
        )
    except LlmError as le:
        return {"status": "error", "code": le.code, "reason": le.message}
    except Exception as e:
        return {"status": "error", "code": "PROVIDER_ERROR", "reason": str(e)}

    # best-effort recording
    try:
        record_llm_usage(provider=provider, model=model, usage=result.usage, flow_id=flow_id, step_id=step_id)
    except Exception:
        pass

    return {
        "status": "ok",
        "provider": provider,
        "model": model,
        "text": result.output_text,
        "usage": {
            "prompt_tokens": result.usage.prompt_tokens,
            "completion_tokens": result.usage.completion_tokens,
            "total_tokens": result.usage.total_tokens,
            "cost_usd": result.usage.cost_usd,
        },
    }


# Optional: auto-register with a step registry if present (no hard dep)
try:  # pragma: no cover
    from tm.steps.registry import register_step  # type: ignore

    register_step(STEP_NAME, run)
except Exception:
    pass
