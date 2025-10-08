from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Literal, Mapping, Optional

import math

from tm.ai.reward_config import RewardWeights

Outcome = Literal["ok", "error", "rejected"]


@dataclass(slots=True)
class FeedbackEvent:
    """Normalized feedback payload emitted by runtime components."""

    outcome: Outcome
    duration_ms: Optional[float] = None
    cost_usd: Optional[float] = None
    user_rating: Optional[float] = None
    task_success: Optional[float] = None
    extras: Dict[str, object] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object], *, default_outcome: Outcome = "error") -> "FeedbackEvent":
        outcome = str(payload.get("outcome") or default_outcome).lower()
        if outcome not in {"ok", "error", "rejected"}:
            outcome = default_outcome
        return cls(
            outcome=outcome,  # type: ignore[arg-type]
            duration_ms=_coerce_float(payload.get("duration_ms")),
            cost_usd=_coerce_float(payload.get("cost_usd")),
            user_rating=_coerce_float(payload.get("user_rating")),
            task_success=_coerce_float(payload.get("task_success")),
            extras={
                k: v
                for k, v in payload.items()
                if k
                not in {
                    "outcome",
                    "duration_ms",
                    "cost_usd",
                    "user_rating",
                    "task_success",
                }
            },
        )


_LATENCY_REF_MS = 100.0
_COST_REF_USD = 0.05


def reward(event: FeedbackEvent, weights: RewardWeights) -> float:
    """Combine feedback metrics into a bounded reward in ``[-1, 1]``."""

    total = 0.0
    total += _outcome_component(event.outcome, weights)
    total += weights.latency_ms * _normalize_latency(event.duration_ms)
    total += weights.cost_usd * _normalize_cost(event.cost_usd)
    total += weights.user_rating * _normalize_rating(event.user_rating)
    total += weights.task_success * _normalize_task_success(event.task_success)
    return max(-1.0, min(1.0, total))


def _outcome_component(outcome: Outcome, weights: RewardWeights) -> float:
    magnitude = abs(weights.outcome_ok)
    if outcome == "ok":
        return magnitude
    if outcome == "rejected":
        return -0.5 * magnitude
    return -magnitude


def _normalize_latency(duration_ms: Optional[float]) -> float:
    if duration_ms is None:
        return 0.0
    value = max(0.0, float(duration_ms))
    if value == 0.0:
        return 0.0
    scaled = math.log1p(value / _LATENCY_REF_MS)
    return math.tanh(scaled)


def _normalize_cost(cost_usd: Optional[float]) -> float:
    if cost_usd is None:
        return 0.0
    value = max(0.0, float(cost_usd))
    if value == 0.0:
        return 0.0
    scaled = math.log1p(value / _COST_REF_USD)
    return math.tanh(scaled)


def _normalize_rating(rating: Optional[float]) -> float:
    if rating is None:
        return 0.0
    return max(-1.0, min(1.0, float(rating)))


def _normalize_task_success(value: Optional[float]) -> float:
    if value is None:
        return 0.0
    return max(-1.0, min(1.0, float(value)))


def _coerce_float(value: object) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


__all__ = ["FeedbackEvent", "Outcome", "reward"]
