from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional


@dataclass(frozen=True)
class DeadLetterRecord:
    entry_id: str
    flow_id: str
    task: Mapping[str, Any]
    error: Mapping[str, Any]
    attempt: int
    timestamp: float
    state: str = "pending"


class DeadLetterStore:
    def __init__(self, dir_path: str) -> None:
        self._dir = Path(dir_path)
        self._pending_dir = self._dir / "pending"
        self._archive_dir = self._dir / "archive"
        self._requeued_dir = self._archive_dir / "requeued"
        self._purged_dir = self._archive_dir / "purged"
        for path in (self._pending_dir, self._requeued_dir, self._purged_dir):
            path.mkdir(parents=True, exist_ok=True)

    def append(
        self, *, flow_id: str, task: Mapping[str, Any], error: Mapping[str, Any], attempt: int
    ) -> DeadLetterRecord:
        ts = time.time()
        entry_id = f"dlq-{int(ts * 1000):013d}-{os.getpid():05d}"
        record = {
            "entry_id": entry_id,
            "flow_id": flow_id,
            "task": dict(task),
            "error": dict(error),
            "attempt": attempt,
            "timestamp": ts,
            "state": "pending",
        }
        path = self._pending_dir / f"{entry_id}.json"
        with path.open("w", encoding="utf-8") as fh:
            json.dump(record, fh, ensure_ascii=False)
        return DeadLetterRecord(
            entry_id=entry_id,
            flow_id=flow_id,
            task=task,
            error=error,
            attempt=attempt,
            timestamp=ts,
            state="pending",
        )

    def list(self) -> Iterable[DeadLetterRecord]:
        for path in sorted(self._pending_dir.glob("*.json")):
            record = self._load_path(path)
            if record is not None:
                yield record

    def load(self, entry_id: str) -> Optional[DeadLetterRecord]:
        path = self._pending_dir / f"{entry_id}.json"
        return self._load_path(path)

    def consume(self, entry_id: str, *, state: str) -> Optional[DeadLetterRecord]:
        path = self._pending_dir / f"{entry_id}.json"
        record = self._load_path(path)
        if record is None:
            return None
        target_dir = self._requeued_dir if state == "requeued" else self._purged_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / path.name
        record_data = {
            "entry_id": record.entry_id,
            "flow_id": record.flow_id,
            "task": dict(record.task),
            "error": dict(record.error),
            "attempt": record.attempt,
            "timestamp": record.timestamp,
            "state": state,
            "consumed_at": time.time(),
        }
        with target_path.open("w", encoding="utf-8") as fh:
            json.dump(record_data, fh, ensure_ascii=False)
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return DeadLetterRecord(
            entry_id=record.entry_id,
            flow_id=record.flow_id,
            task=record.task,
            error=record.error,
            attempt=record.attempt,
            timestamp=record.timestamp,
            state=state,
        )

    def _load_path(self, path: Path) -> Optional[DeadLetterRecord]:
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(data, Mapping):
            return None
        entry_id = data.get("entry_id")
        flow_id = data.get("flow_id")
        task = data.get("task")
        error = data.get("error")
        attempt = data.get("attempt")
        timestamp = data.get("timestamp")
        state = data.get("state", "pending")
        if not isinstance(entry_id, str) or not isinstance(flow_id, str):
            return None
        if not isinstance(task, Mapping) or not isinstance(error, Mapping):
            return None
        if not isinstance(attempt, int) or not isinstance(timestamp, (int, float)):
            return None
        return DeadLetterRecord(
            entry_id=entry_id,
            flow_id=flow_id,
            task=task,
            error=error,
            attempt=attempt,
            timestamp=float(timestamp),
            state=str(state),
        )


__all__ = ["DeadLetterStore", "DeadLetterRecord"]
