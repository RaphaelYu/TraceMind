from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from typing import Any, Callable, Dict, Iterable, Mapping, Optional

from .bandit import EpsilonGreedy, UCB1
from .base import TunerStrategy
from tm.obs import counters
from tm.obs.recorder import Recorder


@dataclass(frozen=True)
class TuningConfig:
    strategy: str
    params: Dict[str, float]
    version: str = "local"
    source: str = "local"


class BanditTuner:
    """Coordinator that manages per-binding bandit strategies."""

    def __init__(
        self,
        strategy: str = "epsilon",
        *,
        epsilon: float = 0.1,
        c: float = 1.0,
        strategy_factory: Optional[Callable[[], TunerStrategy]] = None,
    ) -> None:
        normalized = _normalize_strategy(strategy)
        if strategy_factory is not None:
            self._factory: Callable[[], TunerStrategy] = strategy_factory
            self._default_config = TuningConfig(strategy=normalized, params={})
        elif normalized == "epsilon":
            eps = float(epsilon)
            self._factory = lambda: EpsilonGreedy(eps)
            self._default_config = TuningConfig(strategy="epsilon", params={"epsilon": eps})
        elif normalized == "ucb1":
            bonus = max(0.0, float(c))
            self._factory = lambda: UCB1(bonus)
            self._default_config = TuningConfig(strategy="ucb1", params={"c": bonus})
        else:
            raise ValueError(f"Unsupported default strategy '{strategy}'")

        self._strategies: Dict[str, TunerStrategy] = {}
        self._configs: Dict[str, TuningConfig] = {}
        self._lock = asyncio.Lock()

    async def choose(self, binding: str, candidates: Iterable[str], *, ctx: Optional[Mapping[str, Any]] = None) -> str:
        arm_list = list(dict.fromkeys(candidates))
        if not arm_list:
            raise ValueError("candidates must be a non-empty iterable")
        async with self._lock:
            strategy = self._ensure_strategy(binding)
            arms = {arm: {} for arm in arm_list}
            choice = strategy.select(binding, binding, arms, ctx)
            if choice not in arms:
                raise ValueError(f"Strategy selected unknown arm '{choice}'")
            counters.metrics.get_counter("tm_tuner_select_total").inc(labels={"flow": binding, "arm": choice})
            Recorder.default().on_tuner_select(binding, choice)
            return choice

    async def update(self, binding: str, arm_id: str, reward: float) -> None:
        async with self._lock:
            strategy = self._ensure_strategy(binding)
            strategy.update(binding, binding, arm_id, reward)
            Recorder.default().on_tuner_reward(binding, arm_id, reward)

    async def configure(
        self,
        binding: str,
        params: Mapping[str, Any],
        *,
        version: str,
        source: str = "remote",
    ) -> TuningConfig:
        async with self._lock:
            strategy_name, strategy_params = _parse_params(params, self._default_config)
            strategy = _build_strategy(strategy_name, strategy_params)
            self._strategies[binding] = strategy
            cfg = TuningConfig(strategy=strategy_name, params=dict(strategy_params), version=version, source=source)
            self._configs[binding] = cfg
            return replace(cfg, params=dict(cfg.params))

    async def config(self, binding: str) -> TuningConfig:
        async with self._lock:
            strategy = self._ensure_strategy(binding)
            cfg = self._configs[binding]
            _ = strategy  # ensure binding created
            return replace(cfg, params=dict(cfg.params))

    async def stats(self, binding: str) -> Dict[str, Dict[str, float]]:
        async with self._lock:
            strategy = self._strategies.get(binding)
            if strategy is None:
                return {}
            snapshot = strategy.stats(binding, binding)
            return {
                arm: {
                    "pulls": snap.pulls,
                    "total_reward": snap.total_reward,
                    "avg_reward": snap.avg_reward,
                }
                for arm, snap in snapshot.items()
            }

    def _ensure_strategy(self, binding: str) -> TunerStrategy:
        strategy = self._strategies.get(binding)
        if strategy is None:
            strategy = self._factory()
            self._strategies[binding] = strategy
            self._configs[binding] = replace(self._default_config, params=dict(self._default_config.params))
        return strategy


def _normalize_strategy(name: str) -> str:
    lowered = name.lower()
    if lowered in {"epsilon", "epsilon_greedy", "eps"}:
        return "epsilon"
    if lowered in {"ucb", "ucb1"}:
        return "ucb1"
    return lowered


def _parse_params(params: Mapping[str, Any], default: TuningConfig) -> tuple[str, Dict[str, float]]:
    strategy_name = _normalize_strategy(str(params.get("strategy", default.strategy)))
    result: Dict[str, float] = {}
    if strategy_name == "epsilon":
        value = params.get("epsilon")
        if value is None and "alpha" in params:
            value = params["alpha"]
        epsilon = float(value) if value is not None else default.params.get("epsilon", 0.1)
        if not 0.0 <= epsilon <= 1.0:
            raise ValueError("epsilon must be in [0, 1]")
        result["epsilon"] = epsilon
    elif strategy_name == "ucb1":
        value = params.get("c")
        if value is None and "exploration_bonus" in params:
            value = params["exploration_bonus"]
        bonus = max(0.0, float(value)) if value is not None else default.params.get("c", 1.0)
        result["c"] = bonus
    else:
        raise ValueError(f"Unsupported strategy '{strategy_name}'")
    return strategy_name, result


def _build_strategy(strategy_name: str, params: Mapping[str, float]) -> TunerStrategy:
    if strategy_name == "epsilon":
        epsilon = params.get("epsilon", 0.1)
        return EpsilonGreedy(epsilon)
    if strategy_name == "ucb1":
        bonus = params.get("c", 1.0)
        return UCB1(bonus)
    raise ValueError(f"Unsupported strategy '{strategy_name}'")


__all__ = ["BanditTuner", "EpsilonGreedy", "UCB1", "TuningConfig"]
