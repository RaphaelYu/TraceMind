from __future__ import annotations

import logging
from typing import Optional, TYPE_CHECKING

from tm.ai.feedback import FeedbackEvent, reward
from tm.ai.reward_config import RewardWeights, load_reward_weights
from tm.ai.retrospect import Retrospect
from tm.ai.tuner import BanditTuner
from tm.flow.runtime import FlowRunRecord

if TYPE_CHECKING:
    from pathlib import Path
    from tm.ai.policy_adapter import PolicyAdapter

logger = logging.getLogger(__name__)


class RunEndPipeline:
    """Bridge runtime completion events into Retrospect and Tuner."""

    def __init__(
        self,
        retrospect: Retrospect,
        tuner: BanditTuner,
        *,
        weights: Optional[RewardWeights] = None,
        weight_source: "Path | str | None" = None,
        policy_adapter: Optional["PolicyAdapter"] = None,
    ) -> None:
        self._retrospect = retrospect
        self._tuner = tuner
        self._weights = weights or load_reward_weights(weight_source)
        self._policy_adapter = policy_adapter

    async def on_run_end(self, record: FlowRunRecord) -> None:
        try:
            record.reward = self._compute_reward(record)
            self._retrospect.ingest(record, record.reward)
            if record.binding and record.reward is not None:
                await self._tuner.update(record.binding, record.selected_flow, record.reward)
                if self._policy_adapter is not None:
                    await self._policy_adapter.post_run(record)
        except Exception:  # pragma: no cover - defensive guard
            logger.exception("run_end pipeline failure")

    def _compute_reward(self, record: FlowRunRecord) -> float:
        outcome = _resolve_outcome(record)
        payload = dict(record.meta)
        payload.update(
            {
                "outcome": outcome,
                "duration_ms": record.duration_ms,
                "cost_usd": record.cost_usd,
                "user_rating": record.user_rating,
                "task_success": record.meta.get("task_success"),
            }
        )
        event = FeedbackEvent.from_mapping(payload, default_outcome=outcome)
        return reward(event, self._weights)


def _resolve_outcome(record: FlowRunRecord) -> str:
    for candidate in (record.outcome, record.status):
        if isinstance(candidate, str):
            lowered = candidate.lower()
            if lowered in {"ok", "success"}:
                return "ok"
            if lowered in {"rejected", "reject"}:
                return "rejected"
            if lowered in {"error", "failed", "failure"}:
                return "error"
    return "error"


__all__ = ["RewardWeights", "RunEndPipeline"]
