from __future__ import annotations

import time
from pathlib import Path

from tm.runtime.dlq import DeadLetterStore
from tm.runtime.idempotency import IdempotencyStore
from tm.runtime.queue.manager import TaskQueueManager
from tm.runtime.queue.memory import InMemoryWorkQueue
from tm.runtime.retry import RetryPolicy, RetrySettings


def test_retry_policy_delay_and_dlq_threshold():
    default = RetrySettings(max_attempts=3, base_ms=100, factor=2.0, jitter_ms=0.0, dlq_after=None)
    policy = RetryPolicy(default, {"flow": RetrySettings(max_attempts=2, base_ms=50, factor=1.0, jitter_ms=0.0, dlq_after=None)})

    decision = policy.decide("flow", attempt=1, error={})
    assert decision.action == "retry"
    assert decision.delay_seconds == 0.05

    decision2 = policy.decide("flow", attempt=3, error={})
    assert decision2.action == "dlq"

    nr_decision = policy.decide("other", attempt=1, error={"retryable": False})
    assert nr_decision.action == "dlq"


def test_manager_retry_then_dlq(tmp_path: Path):
    queue = InMemoryWorkQueue()
    idem = IdempotencyStore(dir_path=str(tmp_path / "idem"))
    dlq_store = DeadLetterStore(str(tmp_path / "dlq"))
    policy = RetryPolicy(RetrySettings(max_attempts=2, base_ms=0.0, factor=1.0, jitter_ms=0.0))
    manager = TaskQueueManager(queue, idem, dead_letters=dlq_store, retry_policy=policy, default_ttl=30.0)

    outcome = manager.enqueue(flow_id="demo", input={"value": 1})
    assert outcome.queued and outcome.envelope is not None

    lease = manager.lease(1, lease_ms=1000)[0]

    # First failure should trigger retry
    decision = manager.handle_failure(lease, error={"error_code": "TEMP", "retryable": True})
    assert decision.action == "retry"

    # Next lease should be attempt 1
    time.sleep(0.01)
    leases = manager.lease(1, lease_ms=1000)
    assert leases
    second = leases[0]
    assert second.envelope.attempt == 1

    # Second failure exceeds max_attempts and should land in DLQ
    decision2 = manager.handle_failure(second, error={"error_code": "TEMP", "retryable": True})
    assert decision2.action == "dlq"

    records = list(dlq_store.list())
    assert len(records) == 1
    record = records[0]
    assert record.flow_id == "demo"
    assert record.attempt == 2
    assert record.error.get("reason") == "max_attempts"


def test_dead_letter_store_roundtrip(tmp_path: Path) -> None:
    store = DeadLetterStore(str(tmp_path / "dlq"))
    record = store.append(flow_id="demo", task={"flow_id": "demo", "input": {}}, error={"error_code": "X"}, attempt=1)
    pending = list(store.list())
    assert pending and pending[0].entry_id == record.entry_id
    consumed = store.consume(record.entry_id, state="purged")
    assert consumed is not None
    assert list(store.list()) == []
