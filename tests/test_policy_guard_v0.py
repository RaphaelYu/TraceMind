from tm.agents.models import EffectIdempotency, EffectRef
from tm.policy.guard import PolicyGuard
from tm.runtime.context import ExecutionContext


def _make_effect() -> EffectRef:
    return EffectRef(
        name="write",
        kind="resource",
        target="state:result",
        idempotency=EffectIdempotency(type="keyed", key_fields=["artifact_id"]),
        rollback=None,
        evidence={"type": "hash"},
    )


def test_policy_guard_allows_explicit_target() -> None:
    ctx = ExecutionContext()
    guard = PolicyGuard()
    effect = _make_effect()
    decision = guard.evaluate(effect, ctx, {"policy": {"allow": ["state:result"]}})
    assert decision.allowed
    assert decision.effect_name == "write"
    assert any(record.kind == "policy_guard" and record.payload["allowed"] for record in ctx.evidence.records())


def test_policy_guard_denies_unknown_target() -> None:
    ctx = ExecutionContext()
    guard = PolicyGuard()
    effect = _make_effect()
    decision = guard.evaluate(effect, ctx, {})
    assert not decision.allowed
    assert "not allowlisted" in decision.reason
