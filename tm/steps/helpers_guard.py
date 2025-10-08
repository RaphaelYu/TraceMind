from __future__ import annotations

from typing import Any, Mapping

from tm.guard import GuardBlockedError, GuardViolation

STEP_NAME = "helpers.guard"


def run(ctx: Mapping[str, Any], state: Any) -> Any:
    governance = ctx.get("governance")
    if governance is None:
        raise RuntimeError("governance manager unavailable for guard step")
    config = ctx.get("config", {}) or {}
    rules = config.get("rules")
    if not rules:
        return state
    decision = governance.evaluate_custom_guard(
        rules,
        state if isinstance(state, Mapping) else {"value": state},
        context={"flow": ctx.get("flow"), "step": ctx.get("step")},
    )
    if decision.allowed:
        return state
    violation = decision.first or (decision.violations[0] if decision.violations else None)
    if violation is None:
        violation = GuardViolation(rule="unknown", path=None, reason="guard_blocked", details=())
    raise GuardBlockedError(violation)


try:  # pragma: no cover - optional auto-registration
    from tm.steps.registry import register_step  # type: ignore

    register_step(STEP_NAME, run)
except Exception:  # pragma: no cover
    pass
