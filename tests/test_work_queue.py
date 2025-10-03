from __future__ import annotations

from pathlib import Path

from tm.runtime.queue.memory import InMemoryWorkQueue
from tm.runtime.queue.file import FileWorkQueue


class _FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def monotonic(self) -> float:
        return self.value

    def advance(self, delta: float) -> None:
        self.value += delta


def test_inmemory_queue_handles_ack_and_expiry(monkeypatch):
    clock = _FakeClock()
    monkeypatch.setattr("tm.runtime.queue.memory.time.monotonic", clock.monotonic)

    queue = InMemoryWorkQueue()
    for idx in range(3):
        queue.put({"idx": idx})

    leased = queue.lease(2, lease_ms=1000)
    assert [task.offset for task in leased] == [0, 1]
    for task in leased:
        queue.ack(task.offset, task.token)

    remaining = queue.lease(1, lease_ms=100)
    assert remaining and remaining[0].offset == 2
    clock.advance(10.0)
    redelivered = queue.lease(1, lease_ms=1000)
    assert [task.offset for task in redelivered] == [remaining[0].offset]


def test_file_queue_persists_and_recovers(tmp_path: Path):
    queue_dir = tmp_path / "queue"
    queue = FileWorkQueue(str(queue_dir), segment_max_bytes=256)
    offsets = [queue.put({"value": n}) for n in range(10)]
    assert offsets == list(range(10))

    # The small segment size should force rotation after a few writes
    log_files = sorted(queue_dir.glob("segment-*.log"))
    assert len(log_files) >= 1

    leased = queue.lease(4, lease_ms=1000)
    assert [task.offset for task in leased] == [0, 1, 2, 3]
    for task in leased[:2]:
        queue.ack(task.offset, task.token)

    # Leave two tasks leased but unacked to simulate crash
    queue.close()

    reopened = FileWorkQueue(str(queue_dir), segment_max_bytes=256)
    recovered = reopened.lease(10, lease_ms=1000)
    recovered_offsets = [task.offset for task in recovered]
    # Offsets 0 and 1 were acked earlier, 2 and 3 should be redelivered
    assert recovered_offsets[:2] == [2, 3]

    for task in recovered:
        reopened.ack(task.offset, task.token)
    reopened.close()

    final = FileWorkQueue(str(queue_dir), segment_max_bytes=256)
    assert final.lease(1, lease_ms=1000) == []
    final.close()


def test_file_queue_compacts_segments(tmp_path: Path):
    queue_dir = tmp_path / "queue"
    queue = FileWorkQueue(str(queue_dir), segment_max_bytes=200)

    first_offsets = [queue.put({"payload": "x" * 16, "i": i}) for i in range(5)]
    leased_first = queue.lease(5, lease_ms=1000)
    for task in leased_first:
        queue.ack(task.offset, task.token)

    # Add enough payload to rotate into a new segment
    for _ in range(8):
        queue.put({"payload": "y" * 64})

    assert len(queue._segments) >= 2
    first_new_offset = queue._segments[1].start_offset

    # Ack any outstanding entries from the first segment to trigger compaction
    pending_old = True
    while pending_old:
        pending_old = False
        batch = queue.lease(4, lease_ms=1000)
        if not batch:
            break
        for task in batch:
            if task.offset < first_new_offset:
                queue.ack(task.offset, task.token)
                pending_old = True
            else:
                queue.nack(task.offset, task.token, requeue=True)

    queue.close()

    # The first segment should be compacted away because all entries were acked
    first_segment = queue_dir / "segment-000001.log"
    assert not first_segment.exists()

    # Remaining segment should still be present with outstanding items
    remaining_logs = sorted(queue_dir.glob("segment-*.log"))
    assert remaining_logs
