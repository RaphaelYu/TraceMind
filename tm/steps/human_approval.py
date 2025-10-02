from __future__ import annotations

from typing import Any, Mapping, Sequence

from tm.governance.hitl import PendingApproval

STEP_NAME = "human.approval"


def _coerce_str(value: Any, default: str = "") -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def _coerce_sequence(value: Any) -> Sequence[str]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [str(item) for item in value if isinstance(item, (str, bytes)) and item]
    return []


def run(ctx: Mapping[str, Any], state: Any) -> Any:
    governance = ctx.get("governance")
    if governance is None:
        raise RuntimeError("governance manager unavailable for human.approval")
    hitl = governance.hitl
    if not hitl.enabled:
        raise RuntimeError("HITL approvals are disabled")

    config = ctx.get("config", {}) or {}
    reason = _coerce_str(config.get("reason"), default="approval required")
    ttl_ms_raw = config.get("ttl_ms")
    ttl_ms = int(ttl_ms_raw) if isinstance(ttl_ms_raw, (int, float)) else None
    default = _coerce_str(config.get("default"), default="deny")
    actors = _coerce_sequence(config.get("actors") or config.get("actor"))

    record = hitl.submit(
        flow=_coerce_str(ctx.get("flow"), default="unknown"),
        step=_coerce_str(ctx.get("step"), default=ctx.get("step_id", "approval")),
        reason=reason,
        requested_by=_coerce_str(ctx.get("run_id"), default="unknown"),
        ttl_ms=ttl_ms,
        default=default,
        actors=actors,
        payload={"state": state},
    )

    raise PendingApproval(record)


try:  # pragma: no cover - optional auto-registration
    from tm.steps.registry import register_step  # type: ignore

    register_step(STEP_NAME, run)
except Exception:  # pragma: no cover
    pass
