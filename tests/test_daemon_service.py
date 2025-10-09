from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tm.daemon import (
    DaemonState,
    StartDaemonResult,
    StopDaemonResult,
    build_paths,
    collect_status,
    load_state,
    start_daemon,
    stop_daemon,
    write_state,
)

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="daemon tests are POSIX-only")
from tm.runtime.queue.file import FileWorkQueue


def test_collect_status_reports_queue_counts(tmp_path: Path) -> None:
    queue_dir = tmp_path / "queue"
    queue_dir.mkdir()
    queue = FileWorkQueue(str(queue_dir))
    for idx in range(3):
        queue.put({"task": idx})
    queue.flush()
    queue.close()

    paths = build_paths(tmp_path / "daemon")
    state = DaemonState(pid=os.getpid(), queue_dir=str(queue_dir), created_at=time.time())
    write_state(paths, state)

    status = collect_status(paths)
    assert status.pid == os.getpid()
    assert status.running is True
    assert status.queue is not None
    assert status.queue.backlog == 3
    assert status.queue.pending == 3
    assert status.queue.inflight == 0
    assert status.stale is False
    assert status.uptime_s is not None and status.uptime_s >= 0


# Signal delivery on Windows is inconsistent and may interrupt pytest itself.
@pytest.mark.skipif(sys.platform == "win32", reason="daemon signal semantics differ on Windows")
def test_stop_daemon_terminates_process(tmp_path: Path) -> None:
    queue_dir = tmp_path / "queue"
    queue_dir.mkdir()
    daemon_dir = tmp_path / "daemon"
    paths = build_paths(daemon_dir)

    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        assert proc.pid is not None
        write_state(paths, DaemonState(pid=proc.pid, queue_dir=str(queue_dir), created_at=time.time()))

        result: StopDaemonResult = stop_daemon(paths, timeout=3.0, poll_interval=0.1, force=True)
        assert result.pid == proc.pid
        assert result.stopped is True
        proc.wait(timeout=5)
    finally:
        if proc.poll() is None:  # pragma: no cover - best effort cleanup
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)

    assert not os.path.exists(paths.pid_file)
    assert not os.path.exists(paths.state_file)


def test_start_daemon_launches_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    queue_dir = tmp_path / "queue"
    queue_dir.mkdir()
    paths = build_paths(tmp_path / "daemon")

    launches: dict[str, list[str]] = {}

    class DummyProc:
        def __init__(self, pid: int) -> None:
            self.pid = pid

        def poll(self) -> None:
            return None

    def fake_popen(cmd, **kwargs):
        launches["cmd"] = cmd
        return DummyProc(pid=54321)

    monkeypatch.setattr("tm.daemon.service.subprocess.Popen", fake_popen)

    result: StartDaemonResult = start_daemon(
        paths,
        command=["python", "-m", "tm.cli", "workers", "start"],
        queue_dir=str(queue_dir),
        metadata={"workers": 2},
    )
    assert result.started is True
    assert result.pid == 54321
    assert "cmd" in launches
    state = load_state(paths)
    assert state is not None and state.pid == 54321
    assert state.metadata.get("workers") == 2


def test_start_daemon_detects_running(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    queue_dir = tmp_path / "queue"
    queue_dir.mkdir()
    paths = build_paths(tmp_path / "daemon")
    write_state(
        paths,
        DaemonState(pid=os.getpid(), queue_dir=str(queue_dir), created_at=time.time(), metadata={"workers": 1}),
    )

    def fail_popen(*args, **kwargs):
        raise AssertionError("popen should not be invoked when daemon already running")

    monkeypatch.setattr("tm.daemon.service.subprocess.Popen", fail_popen)

    result = start_daemon(
        paths,
        command=["python", "-m", "tm.cli"],
        queue_dir=str(queue_dir),
    )
    assert result.started is False
    assert result.reason == "already-running"
    assert result.pid == os.getpid()


def test_start_daemon_handles_launch_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    queue_dir = tmp_path / "queue"
    queue_dir.mkdir()
    paths = build_paths(tmp_path / "daemon")

    def raising_popen(*args, **kwargs):
        raise OSError("boom")

    monkeypatch.setattr("tm.daemon.service.subprocess.Popen", raising_popen)

    result = start_daemon(
        paths,
        command=["python", "-m", "tm.cli"],
        queue_dir=str(queue_dir),
    )
    assert result.started is False
    assert result.reason and result.reason.startswith("launch-error")
    assert load_state(paths) is None
