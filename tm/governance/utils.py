"""Utility helpers shared across governance modules."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Iterable, Tuple


@dataclass
class RollingEntry:
    timestamp: float
    value: float


class RollingWindow:
    """Maintain totals over a sliding time window."""

    __slots__ = ("_window", "_entries", "_total")

    def __init__(self, window_sec: float) -> None:
        self._window = float(max(window_sec, 0.0))
        self._entries: Deque[RollingEntry] = deque()
        self._total: float = 0.0

    def observe(self, value: float, *, timestamp: float) -> None:
        if self._window <= 0.0:
            return
        self._prune(timestamp)
        entry = RollingEntry(timestamp=timestamp, value=float(value))
        self._entries.append(entry)
        self._total += entry.value

    def total(self, *, timestamp: float) -> float:
        if self._window <= 0.0:
            return 0.0
        self._prune(timestamp)
        return self._total

    def reset(self) -> None:
        self._entries.clear()
        self._total = 0.0

    def extend(self, entries: Iterable[Tuple[float, float]]) -> None:
        self._entries.extend(RollingEntry(timestamp=t, value=v) for t, v in entries)
        self._total = sum(entry.value for entry in self._entries)

    def _prune(self, current_ts: float) -> None:
        cutoff = current_ts - self._window
        while self._entries and self._entries[0].timestamp <= cutoff:
            entry = self._entries.popleft()
            self._total -= entry.value


__all__ = ["RollingEntry", "RollingWindow"]
