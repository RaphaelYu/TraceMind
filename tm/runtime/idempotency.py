from __future__ import annotations

import json
import os
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

try:
    import fcntl  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None  # type: ignore


@dataclass
class IdempotencyResult:
    status: str
    output: Mapping[str, Any]
    error: Optional[Mapping[str, Any]] = None

    def to_payload(self) -> Mapping[str, Any]:
        return {
            "status": self.status,
            "output": dict(self.output),
            "error": dict(self.error) if isinstance(self.error, Mapping) else None,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "IdempotencyResult":
        status = str(payload.get("status") or "")
        if not status:
            raise ValueError("idempotency payload missing status")
        output = payload.get("output") or {}
        error = payload.get("error")
        if not isinstance(output, Mapping):
            raise TypeError("idempotency output must be mapping")
        if error is not None and not isinstance(error, Mapping):
            raise TypeError("idempotency error must be mapping")
        return cls(status=status, output=dict(output), error=dict(error) if isinstance(error, Mapping) else None)


@dataclass
class _Entry:
    result: IdempotencyResult
    expires_at: float
    created_at: float


class IdempotencyStore:
    """Process-safe cache of task results used to short-circuit duplicate executions."""

    def __init__(
        self,
        *,
        dir_path: str,
        capacity: int = 1024,
        snapshot_interval: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._dir = Path(dir_path)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "idempotency.json"
        self._lock = threading.Lock()
        self._capacity = capacity
        self._clock = clock
        self._snapshot_interval = max(snapshot_interval, 1.0)
        self._last_snapshot = 0.0
        self._entries: OrderedDict[str, _Entry] = OrderedDict()
        self._load()

    # ------------------------------------------------------------------
    def get(self, key: str) -> Optional[IdempotencyResult]:
        now = self._clock()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                self._entries.pop(key, None)
                return None
            # move to end for LRU ordering
            self._entries.move_to_end(key)
            return entry.result

    def remember(self, key: str, result: IdempotencyResult, ttl_seconds: float) -> None:
        if ttl_seconds <= 0:
            return
        expires_at = self._clock() + ttl_seconds
        record = _Entry(result=result, expires_at=expires_at, created_at=self._clock())
        with self._lock:
            self._entries[key] = record
            self._entries.move_to_end(key)
            self._enforce_capacity()
            self._maybe_snapshot_locked()

    def prune(self) -> None:
        now = self._clock()
        with self._lock:
            expired = [key for key, entry in self._entries.items() if entry.expires_at <= now]
            for key in expired:
                self._entries.pop(key, None)
            self._maybe_snapshot_locked(force=True)

    # ------------------------------------------------------------------
    def _enforce_capacity(self) -> None:
        while len(self._entries) > self._capacity:
            self._entries.popitem(last=False)

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            return
        entries = data.get("entries") if isinstance(data, Mapping) else None
        if not isinstance(entries, list):
            return
        now = self._clock()
        for item in entries:
            if not isinstance(item, Mapping):
                continue
            key = item.get("key")
            if not isinstance(key, str):
                continue
            expires_at = item.get("expires_at")
            if not isinstance(expires_at, (int, float)):
                continue
            if expires_at <= now:
                continue
            payload = item.get("result")
            if not isinstance(payload, Mapping):
                continue
            try:
                result = IdempotencyResult.from_payload(payload)
            except Exception:
                continue
            self._entries[key] = _Entry(result=result, expires_at=float(expires_at), created_at=now)
        self._enforce_capacity()

    def _maybe_snapshot_locked(self, force: bool = False) -> None:
        now = self._clock()
        if not force and now - self._last_snapshot < self._snapshot_interval:
            return
        snapshot = {
            "entries": [
                {
                    "key": key,
                    "expires_at": entry.expires_at,
                    "result": entry.result.to_payload(),
                }
                for key, entry in self._entries.items()
                if entry.expires_at > now
            ]
        }
        tmp_path = self._path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(snapshot, fh, separators=(",", ":"))
            fh.flush()
            os.fsync(fh.fileno())
        self._replace_file(tmp_path, self._path)
        self._last_snapshot = now

    def _replace_file(self, src: Path, dst: Path) -> None:
        if fcntl is None:
            os.replace(src, dst)
            return
        with open(dst, "a+b") as target:
            fcntl.flock(target.fileno(), fcntl.LOCK_EX)
            try:
                os.replace(src, dst)
            finally:
                fcntl.flock(target.fileno(), fcntl.LOCK_UN)


__all__ = ["IdempotencyStore", "IdempotencyResult"]
