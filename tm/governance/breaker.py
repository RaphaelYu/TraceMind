"""Circuit breaker implementation with rolling failure windows."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .config import BreakerSettings
from .utils import RollingWindow


class BreakerState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class BreakerDecision:
    allowed: bool
    state: BreakerState
    reason: Optional[str] = None


class CircuitBreaker:
    """Per-scope circuit breaker supporting open/half-open/closed states."""

    __slots__ = (
        "_settings",
        "_failures",
        "_timeouts",
        "_state",
        "_opened_at",
        "_half_open_inflight",
    )

    def __init__(self, settings: BreakerSettings) -> None:
        self._settings = settings
        self._failures = RollingWindow(settings.window_sec)
        self._timeouts = RollingWindow(settings.window_sec)
        self._state = BreakerState.CLOSED
        self._opened_at: float | None = None
        self._half_open_inflight = 0

    @property
    def state(self) -> BreakerState:
        return self._state

    def can_execute(self, *, now: float) -> BreakerDecision:
        if not self._settings.enabled:
            return BreakerDecision(True, state=BreakerState.CLOSED)

        if self._state is BreakerState.OPEN:
            if self._opened_at is None:
                self._opened_at = now
                return BreakerDecision(False, state=self._state, reason="CIRCUIT_OPEN")
            if now - self._opened_at >= self._settings.cooldown_sec:
                self._transition_to_half_open()
            else:
                return BreakerDecision(False, state=self._state, reason="CIRCUIT_OPEN")

        if self._state is BreakerState.HALF_OPEN:
            if self._half_open_inflight >= max(1, self._settings.half_open_max_calls):
                return BreakerDecision(False, state=self._state, reason="CIRCUIT_OPEN")
            self._half_open_inflight += 1
            return BreakerDecision(True, state=self._state)

        # CLOSED state: check rolling thresholds before accepting the call
        if self._should_trip(now):
            self._trip(now)
            return BreakerDecision(False, state=self._state, reason="CIRCUIT_OPEN")
        return BreakerDecision(True, state=self._state)

    def record_success(self, *, now: float) -> None:
        if not self._settings.enabled:
            return
        if self._state is BreakerState.HALF_OPEN:
            self._reset()
        elif self._state is BreakerState.CLOSED:
            # Success while closed: no action beyond pruning window
            self._failures.total(timestamp=now)
            self._timeouts.total(timestamp=now)
        elif self._state is BreakerState.OPEN:
            # Unexpected success while open: treat as half-open evaluation success
            self._reset()

    def record_failure(self, *, now: float, timeout: bool = False) -> None:
        if not self._settings.enabled:
            return
        if timeout:
            self._timeouts.observe(1.0, timestamp=now)
        else:
            self._failures.observe(1.0, timestamp=now)

        if self._state is BreakerState.HALF_OPEN:
            # Any failure during half-open trips immediately
            self._trip(now)
            return

        if self._state is BreakerState.CLOSED and self._should_trip(now):
            self._trip(now)

    def release_half_open_slot(self) -> None:
        if self._half_open_inflight > 0:
            self._half_open_inflight -= 1

    def _should_trip(self, now: float) -> bool:
        fail_threshold = max(0, self._settings.failure_threshold)
        timeout_threshold = max(0, self._settings.timeout_threshold)

        if fail_threshold and self._failures.total(timestamp=now) >= float(fail_threshold):
            return True
        if timeout_threshold and self._timeouts.total(timestamp=now) >= float(timeout_threshold):
            return True
        return False

    def _trip(self, now: float) -> None:
        self._state = BreakerState.OPEN
        self._opened_at = now
        self._half_open_inflight = 0

    def _transition_to_half_open(self) -> None:
        self._state = BreakerState.HALF_OPEN
        self._half_open_inflight = 0

    def _reset(self) -> None:
        self._state = BreakerState.CLOSED
        self._opened_at = None
        self._half_open_inflight = 0
        self._failures.reset()
        self._timeouts.reset()


__all__ = [
    "BreakerDecision",
    "BreakerSettings",
    "BreakerState",
    "CircuitBreaker",
]
