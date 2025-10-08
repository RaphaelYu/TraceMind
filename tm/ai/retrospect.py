from __future__ import annotations

import threading
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque, Dict, Iterable, Optional

from tm.flow.runtime import FlowRunRecord


@dataclass
class AggregateMetrics:
    n: int
    ok_rate: float
    avg_reward: float
    avg_latency_ms: float
    avg_cost_usd: float


@dataclass
class _Entry:
    end_ts: float
    status: str
    reward: float
    duration_ms: float
    cost_usd: float


class Retrospect:
    """In-memory rolling window aggregator for flow run records."""

    def __init__(self, *, window_seconds: float = 300.0) -> None:
        retention = max(1.0, float(window_seconds))
        self._retention_seconds = retention
        self._entries: Dict[str, Deque[_Entry]] = defaultdict(deque)
        self._latest_ts: Dict[str, float] = defaultdict(float)
        self._lock = threading.RLock()

    def ingest(self, record: FlowRunRecord, reward: Optional[float]) -> None:
        binding = record.binding or record.flow
        end_ts = record.end_ts
        entry = _Entry(
            end_ts=end_ts,
            status=(record.status or "error").lower(),
            reward=float(reward or 0.0),
            duration_ms=float(record.duration_ms or 0.0),
            cost_usd=float(record.cost_usd or 0.0),
        )
        with self._lock:
            runs = self._entries[binding]
            runs.append(entry)
            self._latest_ts[binding] = max(self._latest_ts[binding], end_ts)
            self._evict_older_than(runs, end_ts - self._retention_seconds)

    def aggregates(self, window_seconds: float, binding: Optional[str] = None) -> Dict[str, AggregateMetrics]:
        window = max(0.0, float(window_seconds))
        with self._lock:
            if binding is not None:
                entries = self._entries.get(binding, deque())
                latest = self._latest_ts.get(binding, 0.0)
                return {binding: self._compute(entries, latest, window)}
            else:
                keys = list(self._entries.keys())
                return {key: self._compute(self._entries[key], self._latest_ts.get(key, 0.0), window) for key in keys}

    def compare(
        self,
        baseline_seconds: float,
        recent_seconds: float,
        *,
        binding: Optional[str] = None,
    ) -> Dict[str, Dict[str, float]]:
        baseline = self.aggregates(baseline_seconds, binding=binding)
        recent = self.aggregates(recent_seconds, binding=binding)
        all_keys = set(baseline) | set(recent)
        return {
            key: {
                "ok_rate": recent.get(key, _ZERO).ok_rate - baseline.get(key, _ZERO).ok_rate,
                "avg_reward": recent.get(key, _ZERO).avg_reward - baseline.get(key, _ZERO).avg_reward,
                "avg_latency_ms": recent.get(key, _ZERO).avg_latency_ms - baseline.get(key, _ZERO).avg_latency_ms,
                "avg_cost_usd": recent.get(key, _ZERO).avg_cost_usd - baseline.get(key, _ZERO).avg_cost_usd,
                "n": recent.get(key, _ZERO).n - baseline.get(key, _ZERO).n,
            }
            for key in all_keys
        }

    def summary(self, binding: Optional[str] = None) -> Dict[str, AggregateMetrics]:
        """Compatibility wrapper returning aggregates for the retention window."""

        return self.aggregates(self._retention_seconds, binding=binding)

    def _compute(self, entries: Iterable[_Entry], latest_ts: float, window: float) -> AggregateMetrics:
        if window == 0.0:
            return AggregateMetrics(n=0, ok_rate=0.0, avg_reward=0.0, avg_latency_ms=0.0, avg_cost_usd=0.0)
        cutoff = latest_ts - window
        count = 0
        ok = 0
        reward_sum = 0.0
        latency_sum = 0.0
        cost_sum = 0.0
        sequence = entries if isinstance(entries, deque) else list(entries)
        for entry in reversed(sequence):
            if entry.end_ts < cutoff:
                break
            count += 1
            if entry.status == "ok":
                ok += 1
            reward_sum += entry.reward
            latency_sum += entry.duration_ms
            cost_sum += entry.cost_usd
        if count == 0:
            return AggregateMetrics(n=0, ok_rate=0.0, avg_reward=0.0, avg_latency_ms=0.0, avg_cost_usd=0.0)
        return AggregateMetrics(
            n=count,
            ok_rate=ok / count,
            avg_reward=reward_sum / count,
            avg_latency_ms=latency_sum / count,
            avg_cost_usd=cost_sum / count,
        )

    def _evict_older_than(self, runs: Deque[_Entry], cutoff: float) -> None:
        while runs and runs[0].end_ts < cutoff:
            runs.popleft()


_ZERO = AggregateMetrics(n=0, ok_rate=0.0, avg_reward=0.0, avg_latency_ms=0.0, avg_cost_usd=0.0)


__all__ = ["AggregateMetrics", "Retrospect"]
