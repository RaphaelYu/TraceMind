"""Non-blocking rate- and concurrency-limits."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .config import LimitSettings
from .utils import RollingWindow

QPS_WINDOW_SEC = 1.0


@dataclass
class RateDecision:
    allowed: bool
    reason: Optional[str] = None


class RateTracker:
    """Enforces QPS + concurrency constraints for a limit scope."""

    __slots__ = ("_settings", "_qps", "_pending", "_active")

    def __init__(self, settings: LimitSettings) -> None:
        self._settings = settings
        self._qps = RollingWindow(QPS_WINDOW_SEC)
        self._pending = 0
        self._active = 0

    @property
    def pending(self) -> int:
        return self._pending

    @property
    def active(self) -> int:
        return self._active

    def check_and_reserve(self, *, now: float) -> RateDecision:
        if not self._settings.enabled:
            return RateDecision(True)

        if self._settings.qps is not None:
            current = self._qps.total(timestamp=now)
            projected = current + self._pending
            if projected >= float(self._settings.qps):
                return RateDecision(False, reason="RATE_LIMITED")

        if self._settings.concurrency is not None:
            if self._active + self._pending >= int(self._settings.concurrency):
                return RateDecision(False, reason="RATE_LIMITED")

        self._pending += 1
        return RateDecision(True)

    def activate(self, *, now: float) -> None:
        if not self._settings.enabled:
            return
        if self._pending > 0:
            self._pending -= 1
        if self._settings.concurrency is not None:
            self._active += 1
        if self._settings.qps is not None:
            self._qps.observe(1.0, timestamp=now)

    def release(self) -> None:
        if not self._settings.enabled:
            return
        if self._settings.concurrency is not None and self._active > 0:
            self._active -= 1

    def cancel_pending(self) -> None:
        if not self._settings.enabled:
            return
        if self._pending > 0:
            self._pending -= 1


__all__ = ["RateDecision", "RateTracker"]
