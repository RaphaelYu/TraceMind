from __future__ import annotations

import multiprocessing as mp
import time
from pathlib import Path

import shutil

from tm.runtime.queue.file import FileWorkQueue


def _enqueue_worker(dir_path: str, start: int, count: int) -> None:
    queue = FileWorkQueue(dir_path)
    for idx in range(start, start + count):
        queue.put({"flow_id": "demo", "input": {"idx": idx}})
    queue.flush()
    queue.close()


def _lease_without_ack(dir_path: str, lease_ms: int) -> None:
    queue = FileWorkQueue(dir_path)
    leases = queue.lease(1, lease_ms)
    if leases:
        time.sleep((lease_ms / 1000.0) * 0.6)
        # drop without ack to simulate crash
    queue.close()


def test_file_queue_supports_multi_process_enqueues(tmp_path: Path) -> None:
    queue_dir = tmp_path / "queue"
    if queue_dir.exists():
        shutil.rmtree(queue_dir)
    queue_dir.mkdir()
    ctx = mp.get_context("spawn")
    workers = [
        ctx.Process(target=_enqueue_worker, args=(str(queue_dir), 0, 50)),
        ctx.Process(target=_enqueue_worker, args=(str(queue_dir), 50, 50)),
    ]
    for proc in workers:
        proc.start()
    for proc in workers:
        proc.join(timeout=5)
        assert proc.exitcode == 0

    queue = FileWorkQueue(str(queue_dir))
    seen = set()
    while True:
        leases = queue.lease(10, 1000)
        if not leases:
            break
        for lease in leases:
            seen.add(lease.task["input"]["idx"])
            queue.ack(lease.offset, lease.token)
    queue.close()
    assert len(seen) == 100


def test_visibility_timeout_across_processes(tmp_path: Path) -> None:
    queue_dir = tmp_path / "queue"
    if queue_dir.exists():
        shutil.rmtree(queue_dir)
    queue_dir.mkdir()
    queue = FileWorkQueue(str(queue_dir))
    queue.put({"input": {"idx": 1}})
    queue.flush()
    queue.close()

    ctx = mp.get_context("spawn")
    proc = ctx.Process(target=_lease_without_ack, args=(str(queue_dir), 100))
    proc.start()
    proc.join(timeout=5)
    assert proc.exitcode == 0

    time.sleep(0.2)

    queue2 = FileWorkQueue(str(queue_dir))
    leases = queue2.lease(1, 1000)
    assert leases, "expected task to become visible again"
    queue2.ack(leases[0].offset, leases[0].token)
    queue2.close()
