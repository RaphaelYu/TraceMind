from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

from tm import cli as tm_cli
from tm.daemon import DaemonStatus, QueueStatus, StartDaemonResult, StopDaemonResult

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="daemon CLI targets POSIX environments")


def test_daemon_start_requires_flag(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.delenv("TM_ENABLE_DAEMON", raising=False)
    with pytest.raises(SystemExit) as exc:
        tm_cli.main(["daemon", "start"])
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "TM_ENABLE_DAEMON" in captured.err


def test_daemon_start_invokes_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("TM_ENABLE_DAEMON", "1")

    queue_dir = tmp_path / "queue"
    idem_dir = tmp_path / "idem"
    dlq_dir = tmp_path / "dlq"
    state_dir = tmp_path / "state"

    captured: dict[str, object] = {}

    def fake_start(
        paths,
        *,
        command,
        queue_dir,
        metadata,
        env,
        stdout,
        stderr,
    ):
        captured["command"] = list(command)
        captured["queue_dir"] = queue_dir
        captured["metadata"] = dict(metadata)
        captured["stdout_is_none"] = stdout is None
        return StartDaemonResult(pid=1234, started=True, metadata=metadata)

    monkeypatch.setattr(tm_cli, "start_daemon", fake_start)

    rc = tm_cli.main(
        [
            "daemon",
            "start",
            "--state-dir",
            str(state_dir),
            "--queue-dir",
            str(queue_dir),
            "--idempotency-dir",
            str(idem_dir),
            "--dlq-dir",
            str(dlq_dir),
            "--workers",
            "2",
            "--runtime",
            "demo:runtime",
        ]
    )
    assert rc == 0
    out, err = capsys.readouterr()
    assert "started daemon pid 1234" in out
    assert "queue:" in out
    assert "workers" in captured["metadata"]
    command_list = captured["command"]
    assert "workers" in command_list and "start" in command_list
    assert Path(queue_dir).exists()
    assert Path(idem_dir).exists()
    assert Path(dlq_dir).exists()


def test_daemon_start_reports_existing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("TM_ENABLE_DAEMON", "1")

    def fake_start(
        paths,
        *,
        command,
        queue_dir,
        metadata,
        env,
        stdout,
        stderr,
    ):
        return StartDaemonResult(pid=4321, started=False, reason="already-running")

    monkeypatch.setattr(tm_cli, "start_daemon", fake_start)

    with pytest.raises(SystemExit) as exc:
        tm_cli.main(
            [
                "daemon",
                "start",
                "--workers",
                "1",
                "--state-dir",
                str(tmp_path / "state"),
                "--queue-dir",
                str(tmp_path / "queue"),
                "--idempotency-dir",
                str(tmp_path / "idem"),
                "--dlq-dir",
                str(tmp_path / "dlq"),
            ]
        )
    assert exc.value.code == 1
    out, err = capsys.readouterr()
    assert "already running" in err


def test_daemon_ps_json_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("TM_ENABLE_DAEMON", "1")

    def fake_collect(paths, queue_dir=None, now=None):
        return DaemonStatus(
            pid=999,
            running=True,
            created_at=time.time() - 5,
            uptime_s=5.0,
            queue=QueueStatus(
                backend="file",
                path=queue_dir or "queue",
                backlog=4,
                pending=3,
                inflight=1,
                oldest_available_at=time.time() - 1,
            ),
            stale=False,
        )

    monkeypatch.setattr(tm_cli, "collect_status", fake_collect)

    rc = tm_cli.main(["daemon", "ps", "--state-dir", str(tmp_path / "state"), "--json"])
    assert rc == 0
    out, err = capsys.readouterr()
    payload = json.loads(out)
    assert payload["running"] is True
    assert payload["queue"]["backlog"] == 4


def test_daemon_stop_success(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("TM_ENABLE_DAEMON", "1")

    def fake_stop(paths, *, timeout, poll_interval, force):
        return StopDaemonResult(pid=888, stopped=True, forced=False)

    monkeypatch.setattr(tm_cli, "stop_daemon", fake_stop)

    rc = tm_cli.main(["daemon", "stop"])
    assert rc == 0
    out, err = capsys.readouterr()
    assert "stopped daemon pid 888" in out


def test_daemon_stop_not_running(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("TM_ENABLE_DAEMON", "1")

    def fake_stop(paths, *, timeout, poll_interval, force):
        return StopDaemonResult(pid=None, stopped=False, forced=False, reason="not-recorded")

    monkeypatch.setattr(tm_cli, "stop_daemon", fake_stop)

    rc = tm_cli.main(["daemon", "stop"])
    assert rc == 0
    out, err = capsys.readouterr()
    assert "daemon not running" in out


def test_daemon_stop_failure(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("TM_ENABLE_DAEMON", "1")

    def fake_stop(paths, *, timeout, poll_interval, force):
        return StopDaemonResult(pid=111, stopped=False, forced=True, reason="timeout")

    monkeypatch.setattr(tm_cli, "stop_daemon", fake_stop)

    with pytest.raises(SystemExit) as exc:
        tm_cli.main(["daemon", "stop"])
    assert exc.value.code == 1
    out, err = capsys.readouterr()
    assert "failed to stop daemon" in err
