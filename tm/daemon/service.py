from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Sequence

from .state import (
    DaemonPaths,
    DaemonState,
    acquire_lock,
    is_process_running,
    load_state,
    remove_state,
    write_state,
)

__all__ = ["StartDaemonResult", "StopDaemonResult", "start_daemon", "stop_daemon"]


@dataclass
class StartDaemonResult:
    """Outcome from launching the daemon process."""

    pid: Optional[int]
    started: bool
    reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "pid": self.pid,
            "started": self.started,
        }
        if self.reason is not None:
            payload["reason"] = self.reason
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload


@dataclass
class StopDaemonResult:
    """Result payload describing the outcome of a stop attempt."""

    pid: Optional[int]
    stopped: bool
    forced: bool
    reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "pid": self.pid,
            "stopped": self.stopped,
            "forced": self.forced,
        }
        if self.reason is not None:
            payload["reason"] = self.reason
        return payload


def start_daemon(
    paths: DaemonPaths,
    *,
    command: Sequence[Any],
    queue_dir: str,
    metadata: Optional[Mapping[str, Any]] = None,
    env: Optional[Mapping[str, str]] = None,
    cwd: Optional[str] = None,
    stdout=None,
    stderr=None,
    triggers_config: Optional[str] = None,
    triggers_queue_dir: Optional[str] = None,
    triggers_idem_dir: Optional[str] = None,
    triggers_dlq_dir: Optional[str] = None,
) -> StartDaemonResult:
    """Launch the daemon process if one is not already running."""

    if not command:
        raise ValueError("command must not be empty")
    command_list = [str(part) for part in command]
    queue_dir = str(queue_dir)

    with acquire_lock(paths):
        state = load_state(paths)
        if state and is_process_running(state.pid):
            return StartDaemonResult(pid=state.pid, started=False, reason="already-running", metadata=state.metadata)

        # Clean up stale state before starting.
        if state:
            remove_state(paths)

        proc_env = dict(env) if env is not None else os.environ.copy()
        try:
            proc = subprocess.Popen(
                command_list,
                env=proc_env,
                cwd=cwd,
                stdout=stdout,
                stderr=stderr,
                close_fds=os.name != "nt",
            )
        except Exception as exc:
            return StartDaemonResult(pid=None, started=False, reason=f"launch-error:{exc.__class__.__name__}")

        if proc.poll() is not None:
            return StartDaemonResult(
                pid=None,
                started=False,
                reason=f"launch-failed:{proc.returncode}",
            )

        meta: Dict[str, Any] = {"command": command_list, "queue_dir": queue_dir}
        if metadata:
            for key, value in metadata.items():
                meta[key] = value
        if triggers_config:
            meta.setdefault("triggers", {})
            meta["triggers"] = {
                "config": triggers_config,
                "queue_dir": triggers_queue_dir or queue_dir,
                "idempotency_dir": triggers_idem_dir or queue_dir,
                "dlq_dir": triggers_dlq_dir or queue_dir,
            }

        write_state(
            paths,
            DaemonState(
                pid=proc.pid,
                queue_dir=queue_dir,
                created_at=time.time(),
                metadata=meta,
            ),
        )
        return StartDaemonResult(pid=proc.pid, started=True, metadata=meta)


def stop_daemon(
    paths: DaemonPaths,
    *,
    timeout: float = 10.0,
    poll_interval: float = 0.25,
    force: bool = True,
) -> StopDaemonResult:
    """Attempt to stop a daemon process recorded at *paths*."""

    with acquire_lock(paths):
        state = load_state(paths)
        if state is None:
            remove_state(paths)
            return StopDaemonResult(pid=None, stopped=False, forced=False, reason="not-recorded")

        pid = int(state.pid)
        if pid <= 0:
            remove_state(paths)
            return StopDaemonResult(pid=None, stopped=False, forced=False, reason="invalid-pid")

        if not is_process_running(pid):
            _reap_if_child(pid)
            remove_state(paths)
            return StopDaemonResult(pid=pid, stopped=False, forced=False, reason="not-running")

        _send_term(pid)
        deadline = time.monotonic() + max(0.0, timeout)
        while time.monotonic() < deadline:
            if not is_process_running(pid):
                _reap_if_child(pid)
                remove_state(paths)
                return StopDaemonResult(pid=pid, stopped=True, forced=False)
            time.sleep(max(0.05, poll_interval))

        if not force:
            return StopDaemonResult(pid=pid, stopped=False, forced=False, reason="timeout")

        if _force_kill(pid):
            # Wait briefly for forced termination to take effect
            forced_deadline = time.monotonic() + max(0.0, timeout)
            while time.monotonic() < forced_deadline:
                if not is_process_running(pid):
                    _reap_if_child(pid)
                    remove_state(paths)
                    return StopDaemonResult(pid=pid, stopped=True, forced=True)
                time.sleep(max(0.05, poll_interval))

        if not is_process_running(pid):
            _reap_if_child(pid)
            remove_state(paths)
            return StopDaemonResult(pid=pid, stopped=True, forced=True)

        return StopDaemonResult(pid=pid, stopped=False, forced=True, reason="failed-to-terminate")


def _send_term(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except PermissionError:  # pragma: no cover - indicates we cannot signal target
        return
    except OSError:  # pragma: no cover - best effort
        return


def _force_kill(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        sig_kill = getattr(signal, "SIGKILL", None)
    except AttributeError:  # pragma: no cover - shouldn't happen
        sig_kill = None
    if sig_kill is not None:
        try:
            os.kill(pid, sig_kill)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:  # pragma: no cover - indicates we cannot signal target
            pass
        except OSError:  # pragma: no cover - fallback to platform specific
            pass
    if os.name == "nt":  # pragma: no cover - exercised in Windows CI
        try:
            import ctypes

            PROCESS_TERMINATE = 0x0001
            windll = getattr(ctypes, "windll", None)
            if windll is None:
                return False
            handle = windll.kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
            if not handle:
                return False
            try:
                result = windll.kernel32.TerminateProcess(handle, 1)
                return bool(result)
            finally:
                windll.kernel32.CloseHandle(handle)
        except Exception:
            return False
    return False


def _reap_if_child(pid: int) -> None:
    if pid <= 0:
        return
    try:
        waitpid = getattr(os, "waitpid")
    except AttributeError:  # pragma: no cover - windows does not expose waitpid
        return
    flags = getattr(os, "WNOHANG", 0)
    try:
        waitpid(pid, flags)
    except ChildProcessError:
        return
    except OSError:  # pragma: no cover - best effort cleanup
        return
