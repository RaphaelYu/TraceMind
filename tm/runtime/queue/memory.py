from __future__ import annotations

import time
import threading
from dataclasses import dataclass
from typing import Any, Dict, Mapping, MutableMapping, Optional, Sequence
import heapq

from .base import LeasedTask, WorkQueue


@dataclass
class _Entry:
    task: Mapping[str, Any]
    available_at: float
    lease_deadline: float = 0.0
    token: str | None = None
    acked: bool = False


class InMemoryWorkQueue(WorkQueue):
    """In-memory queue used for tests and development."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._next_offset = 0
        self._entries: Dict[int, _Entry] = {}
        self._ready: list[tuple[float, int]] = []
        self._lease_seq = 0

    def put(self, task: Mapping[str, Any]) -> int:
        payload: Mapping[str, Any]
        if isinstance(task, MutableMapping):
            payload = dict(task)
        else:
            payload = task
        with self._lock:
            offset = self._next_offset
            self._next_offset += 1
            available_at = _extract_available_at(payload)
            self._entries[offset] = _Entry(task=payload, available_at=available_at)
            heapq.heappush(self._ready, (available_at, offset))
            return offset

    def lease(self, count: int, lease_ms: int) -> Sequence[LeasedTask]:
        if count <= 0:
            return []
        deadline_delta = max(lease_ms, 0) / 1000.0
        now = time.monotonic()
        leased: list[LeasedTask] = []
        with self._lock:
            self._release_expired(now)
            while self._ready and len(leased) < count:
                available_at, offset = heapq.heappop(self._ready)
                if available_at > now:
                    heapq.heappush(self._ready, (available_at, offset))
                    break
                entry = self._entries.get(offset)
                if entry is None or entry.acked:
                    continue
                self._lease_seq += 1
                token = f"lease-{self._lease_seq}"
                entry.token = token
                entry.lease_deadline = now + deadline_delta
                leased.append(
                    LeasedTask(
                        offset=offset,
                        task=entry.task,
                        lease_deadline=entry.lease_deadline,
                        token=token,
                    )
                )
        return leased

    def ack(self, offset: int, token: str) -> None:
        with self._lock:
            entry = self._entries.get(offset)
            if entry is None or entry.acked:
                return
            if entry.token != token:
                return
            entry.acked = True
            entry.token = None
            entry.lease_deadline = 0.0
            self._entries.pop(offset, None)

    def nack(self, offset: int, token: str, *, requeue: bool = True) -> None:
        with self._lock:
            entry = self._entries.get(offset)
            if entry is None or entry.acked:
                return
            if entry.token != token:
                return
            entry.token = None
            entry.lease_deadline = 0.0
            if requeue:
                available_at = entry.available_at
                now = time.monotonic()
                if available_at < now:
                    available_at = now
                    entry.available_at = available_at
                heapq.heappush(self._ready, (available_at, offset))
            else:
                entry.acked = True
                self._entries.pop(offset, None)

    def reschedule(self, offset: int, *, available_at: float) -> None:
        with self._lock:
            entry = self._entries.get(offset)
            if entry is None or entry.acked:
                return
            entry.available_at = available_at
            if entry.token is None:
                heapq.heappush(self._ready, (available_at, offset))

    def _release_expired(self, now: float) -> None:
        for offset, entry in list(self._entries.items()):
            if entry.acked or entry.token is None:
                continue
            if entry.lease_deadline <= now:
                entry.token = None
                entry.lease_deadline = 0.0
                heapq.heappush(self._ready, (entry.available_at, offset))

    def flush(self) -> None:  # pragma: no cover - nothing to flush
        return

    def close(self) -> None:  # pragma: no cover - nothing to close
        return

    def pending_count(self) -> int:
        with self._lock:
            return len(self._entries)

    def oldest_available_at(self) -> Optional[float]:
        with self._lock:
            candidates = [entry.available_at for entry in self._entries.values() if entry.token is None]
        if not candidates:
            return None
        return min(candidates)


def _extract_available_at(task: Mapping[str, Any]) -> float:
    try:
        scheduled = float(task.get("scheduled_at", 0.0))
    except Exception:
        scheduled = 0.0
    now_wall = time.time()
    now_monotonic = time.monotonic()
    if scheduled <= 0:
        return now_monotonic
    delay = max(0.0, scheduled - now_wall)
    return now_monotonic + delay
