from __future__ import annotations

import time
from pathlib import Path

import importlib

from tm.runtime.dlq import DeadLetterStore
from tm.runtime.idempotency import IdempotencyResult, IdempotencyStore
from tm.runtime.queue.memory import InMemoryWorkQueue
import tm.runtime.queue.manager as queue_manager_module
import tm.obs.counters as counters


def _counter_has(name: str, labels: dict[str, str] | None = None) -> bool:
    snapshot = counters.metrics.snapshot()["counters"].get(name, [])
    target = labels or {}
    for label_items, _ in snapshot:
        label_map = {k: v for k, v in label_items}
        if all(label_map.get(k) == v for k, v in target.items()):
            return True
    return False


def _gauge_value(name: str, labels: dict[str, str] | None = None) -> float:
    snapshot = counters.metrics.snapshot()["gauges"].get(name, [])
    target = labels or {}
    for label_items, value in snapshot:
        label_map = {k: v for k, v in label_items}
        if label_map == target:
            return float(value)
    return 0.0


class _Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def tick(self) -> float:
        return self.value

    def advance(self, delta: float) -> None:
        self.value += delta


def _fresh_manager(*, queue=None, store=None, dlq=None, default_ttl: float = 10.0, **kwargs):
    counters.metrics = counters.Registry()
    global queue_manager_module
    queue_manager_module = importlib.reload(queue_manager_module)
    queue = queue or InMemoryWorkQueue()
    if store is None:
        store = IdempotencyStore(dir_path="/tmp/idem")
    return queue_manager_module.TaskQueueManager(queue, store, dead_letters=dlq, default_ttl=default_ttl, **kwargs)


def test_task_queue_manager_enforces_idempotency(tmp_path: Path):
    clock = _Clock()
    store = IdempotencyStore(
        dir_path=str(tmp_path / "idem"),
        capacity=32,
        snapshot_interval=0.05,
        clock=clock.tick,
    )
    manager = _fresh_manager(queue=InMemoryWorkQueue(), store=store, default_ttl=10.0)

    outcome = manager.enqueue(flow_id="demo", input={"x": 1}, headers={"idempotency_key": "K"})
    assert outcome.queued is True and outcome.envelope is not None

    duplicate = manager.enqueue(flow_id="demo", input={"x": 1}, headers={"idempotency_key": "K"})
    assert duplicate.queued is False
    assert duplicate.cached_result is None

    leases = manager.lease(5, lease_ms=1000)
    assert len(leases) == 1
    lease = leases[0]
    assert lease.envelope.flow_id == "demo"

    manager.ack(lease)
    result = IdempotencyResult(status="ok", output={"value": 2})
    manager.record_result(lease.envelope, result, ttl=10.0)

    cached = manager.enqueue(flow_id="demo", input={"x": 1}, headers={"idempotency_key": "K"})
    assert cached.cached_result is not None
    assert cached.cached_result.status == "ok"
    assert cached.queued is False

    clock.advance(50.0)
    fresh = manager.enqueue(flow_id="demo", input={"x": 1}, headers={"idempotency_key": "K"})
    assert fresh.queued is True


def test_task_queue_metrics(tmp_path: Path):
    counters.metrics = counters.Registry()
    global queue_manager_module
    queue_manager_module = importlib.reload(queue_manager_module)
    queue = InMemoryWorkQueue()
    store = IdempotencyStore(dir_path=str(tmp_path / "idem"))
    dlq = DeadLetterStore(str(tmp_path / "dlq"))
    manager = _fresh_manager(queue=queue, store=store, dlq=dlq, default_ttl=10.0)
    flow = "metrics-test"

    outcome = manager.enqueue(flow_id=flow, input={"idx": 1})
    assert outcome.queued
    assert _counter_has("tm_queue_enqueued_total", {"flow": flow})
    assert _gauge_value("tm_queue_depth") >= 1

    leases = manager.lease(1, lease_ms=1000)
    assert leases
    assert _gauge_value("tm_queue_inflight") >= 1

    manager.ack(leases[0])
    assert _counter_has("tm_queue_acked_total", {"flow": flow})
    assert _gauge_value("tm_queue_depth") == 0
    assert _gauge_value("tm_queue_inflight") == 0

    outcome2 = manager.enqueue(flow_id=flow, input={"idx": 2}, headers={"idempotency_key": "same"})
    assert outcome2.queued
    lease2 = manager.lease(1, lease_ms=1000)[0]
    manager.ack(lease2)
    manager.record_result(lease2.envelope, IdempotencyResult(status="ok", output={}), ttl=10.0)
    cached = manager.enqueue(flow_id=flow, input={"idx": 2}, headers={"idempotency_key": "same"})
    assert not cached.queued
    assert _counter_has("tm_queue_idempo_hits_total", {"flow": flow})

    outcome_retry = manager.enqueue(flow_id=flow, input={"idx": 3})
    assert outcome_retry.queued
    lease_retry = manager.lease(1, lease_ms=1000)[0]
    manager.record_retry(lease_retry, delay_seconds=0.0)
    assert _counter_has("tm_queue_redelivered_total", {"flow": flow})
    assert _counter_has("tm_retries_total", {"flow": flow})

    # Next delivery should be available quickly
    timeout = time.time() + 1.0
    lease_dlq = None
    while time.time() < timeout:
        leases = manager.lease(1, lease_ms=1000)
        if leases:
            lease_dlq = leases[0]
            break
        time.sleep(0.01)
    assert lease_dlq is not None
    manager.record_dead_letter(lease_dlq, error={"error_code": "X"}, reason="forced")
    assert _counter_has("tm_dlq_total", {"flow": flow, "reason": "forced"})
    assert _gauge_value("tm_queue_depth") == 0
    assert _gauge_value("tm_queue_inflight") == 0
