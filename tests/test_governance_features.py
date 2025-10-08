from __future__ import annotations

from dataclasses import dataclass

import pytest

from tm.flow.flow import Flow
from tm.flow.runtime import FlowRuntime
from tm.flow.spec import FlowSpec, StepDef
from tm.flow.operations import Operation
from tm.governance.config import (
    AuditConfig,
    BreakerConfig,
    GuardConfig,
    HitlConfig,
    LimitSettings,
    LimitsConfig,
    GovernanceConfig,
)
from tm.governance.manager import GovernanceManager
from tm.steps import human_approval as human_approval_step


@dataclass
class DummyFlow(Flow):
    spec_obj: FlowSpec

    @property
    def name(self) -> str:  # pragma: no cover - simple proxy
        return self.spec_obj.name

    def spec(self) -> FlowSpec:  # pragma: no cover - simple proxy
        return self.spec_obj


@pytest.mark.asyncio
async def test_guard_blocks_request(monkeypatch):
    spec = FlowSpec(name="guarded")
    spec.add_step(StepDef("start", Operation.TASK))
    flow = DummyFlow(spec)
    config = GovernanceConfig(
        enabled=True,
        limits=LimitsConfig(enabled=False),
        breaker=BreakerConfig(enabled=False),
        guard=GuardConfig(
            enabled=True,
            global_rules=({"type": "length_max", "path": "$.text", "value": 3},),
        ),
        hitl=HitlConfig(enabled=False),
        audit=AuditConfig(enabled=False),
    )
    manager = GovernanceManager(config)
    runtime = FlowRuntime({spec.name: flow}, governance=manager)

    result = await runtime.run("guarded", inputs={"text": "blocked"})

    assert result["status"] == "error"
    assert result["error_code"] == "GUARD_BLOCKED"

    await runtime.aclose()


@pytest.mark.asyncio
async def test_rate_limit_rejects_second_request():
    spec = FlowSpec(name="limited")
    spec.add_step(StepDef("start", Operation.TASK))
    flow = DummyFlow(spec)

    class Clock:
        def __init__(self):
            self.value = 0.0

        def __call__(self) -> float:
            return self.value

        def advance(self, delta: float) -> None:
            self.value += delta

    clock = Clock()
    config = GovernanceConfig(
        enabled=True,
        limits=LimitsConfig(
            enabled=True,
            global_scope=LimitSettings(enabled=True, qps=1.0),
        ),
        breaker=BreakerConfig(enabled=False),
        guard=GuardConfig(enabled=False),
        hitl=HitlConfig(enabled=False),
        audit=AuditConfig(enabled=False),
    )
    manager = GovernanceManager(config, clock=clock)
    runtime = FlowRuntime({spec.name: flow}, governance=manager)

    ok = await runtime.run("limited")
    assert ok["status"] == "ok"

    denied = await runtime.run("limited")
    assert denied["status"] == "rejected"
    assert denied["error_code"] == "RATE_LIMITED"

    clock.advance(2.0)
    allowed = await runtime.run("limited")
    assert allowed["status"] == "ok"

    await runtime.aclose()


@pytest.mark.asyncio
async def test_human_approval_returns_pending():
    async def approval_runner(ctx, state):
        return human_approval_step.run(ctx, state)

    spec = FlowSpec(name="needs-approval")
    spec.add_step(StepDef("approval", Operation.TASK, run=approval_runner))
    flow = DummyFlow(spec)
    config = GovernanceConfig(
        enabled=True,
        limits=LimitsConfig(enabled=False),
        breaker=BreakerConfig(enabled=False),
        guard=GuardConfig(enabled=False),
        hitl=HitlConfig(enabled=True, default_ttl_ms=1000),
        audit=AuditConfig(enabled=False),
    )
    manager = GovernanceManager(config)
    runtime = FlowRuntime({spec.name: flow}, governance=manager)

    result = await runtime.run("needs-approval", inputs={"value": 1})

    assert result["status"] == "pending"
    approval_id = result["output"].get("approval_id")
    assert approval_id

    record = manager.hitl.get(approval_id)
    assert record is not None
    decided = manager.hitl.decide(approval_id, decision="approve", actor="tester")
    assert decided.status == "approve"

    await runtime.aclose()
