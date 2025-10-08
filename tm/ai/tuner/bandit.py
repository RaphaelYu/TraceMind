from __future__ import annotations

import math
import random
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, Mapping, Optional, Tuple

from .base import ArmSnapshot, TunerStrategy


@dataclass
class _ArmState:
    pulls: int = 0
    total_reward: float = 0.0

    @property
    def avg_reward(self) -> float:
        if self.pulls == 0:
            return 0.0
        return self.total_reward / self.pulls


class _BanditState:
    def __init__(self) -> None:
        self.arms: Dict[str, _ArmState] = {}
        self.total_pulls: int = 0


class _BanditStrategy(TunerStrategy):
    def __init__(self) -> None:
        self._state: Dict[Tuple[str, str], _BanditState] = defaultdict(_BanditState)

    def _resolve_state(self, flow_id: str, policy_id: str) -> _BanditState:
        return self._state[(flow_id, policy_id)]

    @staticmethod
    def _arm_ids(arms: Mapping[str, Mapping[str, object]] | Mapping[str, object]) -> Iterable[str]:
        if isinstance(arms, Mapping):
            return list(arms.keys())
        return list(arms)

    @staticmethod
    def _ensure_arm(state: _BanditState, arm_id: str) -> _ArmState:
        return state.arms.setdefault(arm_id, _ArmState())

    def stats(self, flow_id: str, policy_id: str) -> Dict[str, ArmSnapshot]:
        state = self._state.get((flow_id, policy_id))
        if state is None:
            return {}
        return {
            arm: ArmSnapshot(pulls=data.pulls, total_reward=data.total_reward, avg_reward=data.avg_reward)
            for arm, data in state.arms.items()
        }


class EpsilonGreedy(_BanditStrategy):
    def __init__(self, epsilon: float = 0.1, *, seed: Optional[int] = None) -> None:
        super().__init__()
        if not 0.0 <= epsilon <= 1.0:
            raise ValueError("epsilon must be in [0, 1]")
        self._epsilon = float(epsilon)
        self._rng = random.Random(seed)

    @property
    def epsilon(self) -> float:
        return self._epsilon

    def select(
        self,
        flow_id: str,
        policy_id: str,
        arms: Mapping[str, Mapping[str, object]] | Mapping[str, object],
        ctx: Optional[Mapping[str, object]] = None,
    ) -> str:
        state = self._resolve_state(flow_id, policy_id)
        arm_ids = list(self._arm_ids(arms))
        if not arm_ids:
            raise ValueError("Cannot select arm from empty set")
        for arm_id in arm_ids:
            self._ensure_arm(state, arm_id)

        unexplored = [arm for arm in arm_ids if state.arms[arm].pulls == 0]
        if unexplored:
            return self._rng.choice(unexplored)

        if self._rng.random() < self._epsilon:
            return self._rng.choice(arm_ids)

        best_value = max(state.arms[arm].avg_reward for arm in arm_ids)
        best = [arm for arm in arm_ids if math.isclose(state.arms[arm].avg_reward, best_value, rel_tol=1e-9)]
        return self._rng.choice(best)

    def update(self, flow_id: str, policy_id: str, arm_id: str, reward: float) -> None:
        state = self._resolve_state(flow_id, policy_id)
        arm = self._ensure_arm(state, arm_id)
        arm.pulls += 1
        arm.total_reward += float(reward)
        state.total_pulls += 1


class UCB1(_BanditStrategy):
    def __init__(self, c: float = 1.0) -> None:
        super().__init__()
        if c < 0.0:
            raise ValueError("c must be >= 0")
        self._c = float(c)

    @property
    def c(self) -> float:
        return self._c

    def select(
        self,
        flow_id: str,
        policy_id: str,
        arms: Mapping[str, Mapping[str, object]] | Mapping[str, object],
        ctx: Optional[Mapping[str, object]] = None,
    ) -> str:
        state = self._resolve_state(flow_id, policy_id)
        arm_ids = list(self._arm_ids(arms))
        if not arm_ids:
            raise ValueError("Cannot select arm from empty set")
        for arm_id in arm_ids:
            self._ensure_arm(state, arm_id)

        unexplored = [arm for arm in arm_ids if state.arms[arm].pulls == 0]
        if unexplored:
            return random.choice(unexplored)

        total_pulls = sum(data.pulls for data in state.arms.values())
        if total_pulls == 0:
            total_pulls = 1
        log_total = math.log(total_pulls)

        def ucb_value(arm_id: str) -> float:
            arm = state.arms[arm_id]
            bonus = 0.0
            if arm.pulls > 0:
                bonus = self._c * math.sqrt(2.0 * log_total / arm.pulls) if self._c > 0.0 else 0.0
            return arm.avg_reward + bonus

        best_value = -math.inf
        best_arm = arm_ids[0]
        for arm_id in arm_ids:
            value = ucb_value(arm_id)
            if value > best_value:
                best_value = value
                best_arm = arm_id
        return best_arm

    def update(self, flow_id: str, policy_id: str, arm_id: str, reward: float) -> None:
        state = self._resolve_state(flow_id, policy_id)
        arm = self._ensure_arm(state, arm_id)
        arm.pulls += 1
        arm.total_reward += float(reward)
        state.total_pulls += 1


__all__ = ["EpsilonGreedy", "UCB1"]
