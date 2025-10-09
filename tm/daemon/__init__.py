"""Support code for TraceMind background daemon."""

from .state import (
    DaemonPaths,
    DaemonState,
    DaemonStatus,
    QueueStatus,
    acquire_lock,
    build_paths,
    collect_status,
    is_process_running,
    load_state,
    remove_state,
    write_state,
)
from .service import StartDaemonResult, StopDaemonResult, start_daemon, stop_daemon

__all__ = [
    "DaemonPaths",
    "DaemonState",
    "DaemonStatus",
    "QueueStatus",
    "StartDaemonResult",
    "StopDaemonResult",
    "acquire_lock",
    "build_paths",
    "collect_status",
    "is_process_running",
    "load_state",
    "remove_state",
    "write_state",
    "start_daemon",
    "stop_daemon",
]
