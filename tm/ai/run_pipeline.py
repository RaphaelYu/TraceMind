from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

from tm.ai.retrospect import Retrospect
from tm.ai.tuner import BanditTuner
from tm.flow.runtime import FlowRunRecord


if TYPE_CHECKING:
    from tm.ai.policy_adapter import PolicyAdapter


logger = logging.getLogger(__name__)


@dataclass
class RewardWeights:
    success: float = 1.0
    failure: float = -1.0
    user_rating: float = 0.25
    latency: float = 0.0
    cost: float = 0.0


class RunEndPipeline:
    """Bridge runtime completion events into Retrospect and Tuner."""

    def __init__(
        self,
        retrospect: Retrospect,
        tuner: BanditTuner,
        *,
        weights: Optional[RewardWeights] = None,
        policy_adapter: Optional["PolicyAdapter"] = None,
    ) -> None:
        self._retrospect = retrospect
        self._tuner = tuner
        self._weights = weights or RewardWeights()
        self._policy_adapter = policy_adapter

    async def on_run_end(self, record: FlowRunRecord) -> None:
        try:
            record.reward = self._compute_reward(record)
            self._retrospect.ingest(record)
            if record.binding and record.reward is not None:
                await self._tuner.update(record.binding, record.selected_flow, record.reward)
                if self._policy_adapter is not None:
                    await self._policy_adapter.post_run(record)
        except Exception:  # pragma: no cover - defensive guard
            logger.exception("run_end pipeline failure")

    def _compute_reward(self, record: FlowRunRecord) -> float:
        base = self._weights.success if record.status == "ok" else self._weights.failure
        if record.user_rating is not None:
            base += self._weights.user_rating * record.user_rating
        if record.cost_usd is not None:
            base += self._weights.cost * record.cost_usd
        if record.duration_ms:
            base += self._weights.latency * record.duration_ms
        return base


__all__ = ["RewardWeights", "RunEndPipeline"]
