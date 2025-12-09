from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional

try:  # pragma: no cover - platform dependent import
    import fcntl
except ModuleNotFoundError:  # pragma: no cover - windows fallback
    fcntl = None  # type: ignore[assignment]

try:  # pragma: no cover - windows specific
    import msvcrt
except ModuleNotFoundError:  # pragma: no cover - non-windows
    msvcrt = None  # type: ignore[assignment]

from tm.runtime.queue.file import FileWorkQueue

__all__ = [
    "DaemonPaths",
    "DaemonState",
    "DaemonStatus",
    "QueueStatus",
    "build_paths",
    "load_state",
    "write_state",
    "collect_status",
    "remove_state",
    "acquire_lock",
    "is_process_running",
]


@dataclass(frozen=True)
class DaemonPaths:
    """Filesystem layout for daemon metadata."""

    root: str
    pid_file: str
    state_file: str
    lock_file: str


@dataclass
class DaemonState:
    """Metadata describing a running daemon process."""

    pid: int
    queue_dir: str
    created_at: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    def uptime(self, *, now: Optional[float] = None) -> Optional[float]:
        reference = now if now is not None else time.time()
        if self.created_at <= 0:
            return None
        return max(0.0, reference - self.created_at)

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "pid": self.pid,
            "queue_dir": self.queue_dir,
            "created_at": self.created_at,
        }
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload

    @staticmethod
    def from_dict(raw: Mapping[str, Any]) -> "DaemonState":
        pid = int(raw.get("pid", 0))
        queue_dir = str(raw.get("queue_dir", ""))
        created_at = float(raw.get("created_at", 0.0))
        meta = raw.get("metadata") or {}
        if not isinstance(meta, dict):
            meta = {}
        return DaemonState(pid=pid, queue_dir=queue_dir, created_at=created_at, metadata=dict(meta))


@dataclass
class QueueStatus:
    """Snapshot of queue health used for CLI reporting."""

    backend: str
    path: str
    backlog: int
    pending: int
    inflight: int
    oldest_available_at: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "backend": self.backend,
            "path": self.path,
            "backlog": self.backlog,
            "pending": self.pending,
            "inflight": self.inflight,
            "oldest_available_at": self.oldest_available_at,
        }


@dataclass
class DaemonStatus:
    """High-level daemon snapshot including queue telemetry."""

    pid: Optional[int]
    running: bool
    created_at: Optional[float]
    uptime_s: Optional[float]
    queue: Optional[QueueStatus]
    stale: bool
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "pid": self.pid,
            "running": self.running,
            "created_at": self.created_at,
            "uptime_s": self.uptime_s,
            "stale": self.stale,
        }
        if self.queue is not None:
            payload["queue"] = self.queue.to_dict()
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload


def build_paths(root: str) -> DaemonPaths:
    """Construct daemon metadata paths rooted at *root*."""

    resolved = os.path.abspath(root)
    os.makedirs(resolved, exist_ok=True)
    return DaemonPaths(
        root=resolved,
        pid_file=os.path.join(resolved, "daemon.pid"),
        state_file=os.path.join(resolved, "daemon.json"),
        lock_file=os.path.join(resolved, "daemon.lock"),
    )


def load_state(paths: DaemonPaths) -> Optional[DaemonState]:
    """Load daemon state if it has been recorded."""

    try:
        with open(paths.state_file, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, dict):
        return None
    try:
        return DaemonState.from_dict(raw)
    except Exception:
        return None


def write_state(paths: DaemonPaths, state: DaemonState) -> None:
    """Persist daemon metadata (PID, queue, timestamps)."""

    data = json.dumps(state.to_dict(), separators=(",", ":"), sort_keys=True)
    _atomic_write(paths.state_file, data)
    _atomic_write(paths.pid_file, f"{state.pid}\n")


def remove_state(paths: DaemonPaths) -> None:
    """Remove persisted daemon metadata."""

    for target in (paths.pid_file, paths.state_file):
        try:
            os.remove(target)
        except FileNotFoundError:
            continue


def collect_status(
    paths: DaemonPaths,
    *,
    queue_dir: Optional[str] = None,
    now: Optional[float] = None,
) -> DaemonStatus:
    """Collect daemon + queue status for CLI/monitoring."""

    state = load_state(paths)
    pid: Optional[int] = state.pid if state else None
    queue_path = queue_dir or (state.queue_dir if state else None)
    running = pid is not None and is_process_running(pid)
    queue_snapshot = _collect_queue_status(queue_path) if queue_path else None
    created_at = state.created_at if state else None
    uptime = state.uptime(now=now) if state and running else None
    stale = bool(pid and not running)
    metadata = state.metadata if state else None
    return DaemonStatus(
        pid=pid,
        running=running,
        created_at=created_at,
        uptime_s=uptime,
        queue=queue_snapshot,
        stale=stale,
        metadata=metadata,
    )


def _collect_queue_status(queue_dir: str) -> QueueStatus:
    if not queue_dir:
        return QueueStatus(
            backend="file",
            path="",
            backlog=0,
            pending=0,
            inflight=0,
            oldest_available_at=None,
        )
    if not os.path.exists(queue_dir):
        return QueueStatus(
            backend="file",
            path=queue_dir,
            backlog=0,
            pending=0,
            inflight=0,
            oldest_available_at=None,
        )
    queue = FileWorkQueue(queue_dir)
    try:
        snapshot = queue.describe()
    finally:
        queue.close()
    return QueueStatus(
        backend="file",
        path=queue_dir,
        backlog=snapshot["backlog"],
        pending=snapshot["pending"],
        inflight=snapshot["inflight"],
        oldest_available_at=snapshot["oldest_available_at"],
    )


def is_process_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # pragma: no cover - rare but indicates running without permission
        return True
    except OSError:
        return False
    try:  # pragma: no cover - only meaningful on POSIX
        waitpid = getattr(os, "waitpid")
    except AttributeError:
        waitpid = None
    if waitpid is not None:
        flags = getattr(os, "WNOHANG", 0)
        try:
            waited_pid, _ = waitpid(pid, flags)
        except ChildProcessError:
            waited_pid = 0
        except OSError:
            waited_pid = 0
        if waited_pid == pid:
            return False
    return True


def _atomic_write(path: str, data: str) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_path, path)


class _FileLock:
    """Cross-platform advisory file lock used to serialize daemon operations."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._fh: Optional[Any] = None

    def __enter__(self) -> "_FileLock":
        directory = os.path.dirname(self._path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        fh = open(self._path, "a+b")
        if fcntl is not None:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        elif msvcrt is not None:  # pragma: no cover - windows only
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
        self._fh = fh
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._fh is None:
            return
        fh = self._fh
        self._fh = None
        if fcntl is not None:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        elif msvcrt is not None:  # pragma: no cover - windows only
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        fh.close()

    @property
    def file(self):
        return self._fh


def acquire_lock(paths: DaemonPaths) -> _FileLock:
    """Acquire the daemon mutation lock."""

    return _FileLock(paths.lock_file)
