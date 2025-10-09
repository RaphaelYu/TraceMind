from __future__ import annotations

import json
from pathlib import Path

import pytest

from tm.runtime.queue.file import FileWorkQueue


def test_file_queue_v2_enables_fsync(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TM_FILE_QUEUE_V2", "1")
    queue_dir = tmp_path / "queue"
    queue = FileWorkQueue(str(queue_dir))
    try:
        assert queue._fsync_on_put is True  # type: ignore[attr-defined]
    finally:
        queue.close()


def test_file_queue_v2_rewrites_corrupt_index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog) -> None:
    monkeypatch.setenv("TM_FILE_QUEUE_V2", "1")
    caplog.set_level("WARNING", logger="tm.runtime.queue.file")
    queue_dir = tmp_path / "queue"
    queue = FileWorkQueue(str(queue_dir))
    queue.put({"flow_id": "demo", "input": {"x": 1}})
    lease = queue.lease(1, 1000)[0]
    queue.ack(lease.offset, lease.token)
    queue.close()

    idx_path = next(queue_dir.glob("segment-*.idx"))
    idx_path.write_text('{"acked":["bad-value"]}', encoding="utf-8")

    queue2 = FileWorkQueue(str(queue_dir))
    try:
        assert "invalid ack entry" in caplog.text
        with open(idx_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        assert isinstance(data.get("acked"), list)
        assert queue2.pending_count() >= 0
    finally:
        queue2.close()


def test_file_queue_v2_uses_msvcrt_locking(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TM_FILE_QUEUE_V2", "1")

    fake_calls: list[int] = []

    class FakeMsvcrt:
        LK_LOCK = 1
        LK_UNLCK = 2

        def locking(self, fileno, mode, nbytes):
            fake_calls.append(mode)

    monkeypatch.setattr("tm.runtime.queue.file.fcntl", None, raising=False)
    monkeypatch.setattr("tm.runtime.queue.file.msvcrt", FakeMsvcrt())

    queue_dir = tmp_path / "queue"
    queue = FileWorkQueue(str(queue_dir))
    queue.put({"flow_id": "demo", "input": {"x": 2}})
    lease = queue.lease(1, 1000)
    assert lease, "expected at least one lease"
    queue.ack(lease[0].offset, lease[0].token)
    queue.close()

    assert FakeMsvcrt.LK_LOCK in fake_calls
    assert FakeMsvcrt.LK_UNLCK in fake_calls
