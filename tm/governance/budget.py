"""Budget trackers for token and cost limits."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple

from .config import LimitSettings
from .utils import RollingWindow

TOKENS_WINDOW_SEC = 60.0
COST_WINDOW_SEC = 3600.0


@dataclass
class BudgetDecision:
    allowed: bool
    reason: Optional[str] = None
    kind: Optional[str] = None


class BudgetTracker:
    """Track rolling usage for tokens and USD cost."""

    __slots__ = ("_settings", "_tokens", "_cost")

    def __init__(self, settings: LimitSettings) -> None:
        self._settings = settings
        self._tokens = RollingWindow(TOKENS_WINDOW_SEC)
        self._cost = RollingWindow(COST_WINDOW_SEC)

    def can_accept(self, *, now: float) -> BudgetDecision:
        if not self._settings.enabled:
            return BudgetDecision(True)

        if self._settings.tokens_per_min is not None:
            current = self._tokens.total(timestamp=now)
            if current >= float(self._settings.tokens_per_min):
                return BudgetDecision(False, reason="BUDGET_EXCEEDED", kind="tokens")

        if self._settings.cost_per_hour is not None:
            current = self._cost.total(timestamp=now)
            if current >= float(self._settings.cost_per_hour):
                return BudgetDecision(False, reason="BUDGET_EXCEEDED", kind="cost")

        return BudgetDecision(True)

    def record(self, *, tokens: Optional[float], cost: Optional[float], now: float) -> None:
        if not self._settings.enabled:
            return
        if tokens is not None and self._settings.tokens_per_min is not None:
            value = max(0.0, float(tokens))
            if not math.isnan(value) and value > 0.0:
                self._tokens.observe(value, timestamp=now)
        if cost is not None and self._settings.cost_per_hour is not None:
            value = max(0.0, float(cost))
            if not math.isnan(value) and value > 0.0:
                self._cost.observe(value, timestamp=now)

    def snapshot(self, *, now: float) -> Tuple[Optional[float], Optional[float]]:
        tokens = None
        if self._settings.tokens_per_min is not None:
            tokens = self._tokens.total(timestamp=now)
        cost = None
        if self._settings.cost_per_hour is not None:
            cost = self._cost.total(timestamp=now)
        return tokens, cost


__all__ = ["BudgetDecision", "BudgetTracker"]
