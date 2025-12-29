from pathlib import Path
from typing import Mapping

from tm.runtime.context import ExecutionContext
from tm.runtime.idempotency import ExecutionIdempotencyGuard


def test_context_ref_store(tmp_path: Path) -> None:
    ctx = ExecutionContext()
    ctx.set_ref("memory", {"value": 1})
    assert ctx.get_ref("memory") == {"value": 1}
    file_target = tmp_path / "state.json"
    ctx.set_ref("disk", {"value": 2}, file_path=file_target)
    assert file_target.exists()
    assert ctx.get_ref("disk") == {"value": 2}


def test_context_event_audit_metric_and_log_records() -> None:
    ctx = ExecutionContext()
    ctx.emit_event("start", {"step": 1})
    ctx.record_audit("init", {"user": "tester"})
    ctx.record_metric("latency", 12.5, tags={"unit": "ms"})
    ctx.log("hello world", level="debug")
    assert ctx.events and ctx.events[-1]["type"] == "start"
    assert ctx.audits[-1]["action"] == "init"
    assert ctx.metrics[-1]["name"] == "latency"
    records = ctx.evidence.records()
    kinds = {record.kind for record in records}
    assert {"event", "audit", "metric", "log"} <= kinds


def test_execution_context_idempotency_guard() -> None:
    guard = ExecutionIdempotencyGuard(ttl_seconds=60.0)
    ctx = ExecutionContext(idempotency_guard=guard)
    calls = []

    def work() -> Mapping[str, int]:
        calls.append(True)
        return {"value": 42}

    first = ctx.run_idempotent("step", work)
    second = ctx.run_idempotent("step", work)
    assert first == second
    assert len(calls) == 1
