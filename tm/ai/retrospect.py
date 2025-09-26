from __future__ import annotations

import threading
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque, Dict, Iterable, Optional

from tm.flow.runtime import FlowRunRecord


@dataclass
class WindowMetrics:
    count: int
    ok_rate: float
    avg_reward: float
    avg_latency_ms: float


class Retrospect:
    """In-memory rolling window aggregator for flow run records."""

    def __init__(self, *, window_seconds: float = 300.0) -> None:
        self._window_seconds = max(1.0, float(window_seconds))
        self._runs: Dict[str, Deque[FlowRunRecord]] = defaultdict(deque)
        self._lock = threading.RLock()

    def ingest(self, record: FlowRunRecord) -> None:
        binding = record.binding or record.flow
        end_ts = record.end_ts
        with self._lock:
            runs = self._runs[binding]
            runs.append(record)
            cutoff = end_ts - self._window_seconds
            while runs and runs[0].end_ts < cutoff:
                runs.popleft()

    def summary(self, binding: Optional[str] = None) -> Dict[str, WindowMetrics]:
        """Return aggregated metrics for ``binding`` or all bindings."""

        with self._lock:
            if binding is not None:
                items: Iterable[tuple[str, Deque[FlowRunRecord]]] = ((binding, self._runs.get(binding, deque())),)
            else:
                items = tuple(self._runs.items())

            return {
                key: self._compute_window_metrics(list(records))
                for key, records in items
            }

    def _compute_window_metrics(self, records: Iterable[FlowRunRecord]) -> WindowMetrics:
        data = list(records)
        total = len(data)
        if total == 0:
            return WindowMetrics(count=0, ok_rate=0.0, avg_reward=0.0, avg_latency_ms=0.0)

        ok = sum(1 for record in data if record.status == "ok")
        reward_sum = sum(record.reward or 0.0 for record in data)
        latency_sum = sum(record.duration_ms for record in data)
        return WindowMetrics(
            count=total,
            ok_rate=ok / total,
            avg_reward=reward_sum / total,
            avg_latency_ms=latency_sum / total,
        )


__all__ = ["Retrospect", "WindowMetrics"]
