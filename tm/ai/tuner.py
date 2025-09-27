from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from asyncio import Lock

import math

from tm.ai.observer import Observation
from tm.ai.proposals import Change, Proposal


@dataclass
class ArmState:
    score: float = 0.0
    pulls: int = 0
    updates: int = 0
    total_reward: float = 0.0

    def apply_reward(self, reward: float, alpha: float) -> None:
        self.updates += 1
        self.total_reward += reward
        if self.updates == 1:
            self.score = reward
        else:
            self.score += alpha * (reward - self.score)

    def seen(self) -> bool:
        return self.pulls > 0 or self.updates > 0


@dataclass
class TuningConfig:
    alpha: float
    exploration_bonus: float
    version: str = "local"
    source: str = "local"

    def clone(self) -> "TuningConfig":
        return TuningConfig(
            alpha=self.alpha,
            exploration_bonus=self.exploration_bonus,
            version=self.version,
            source=self.source,
        )


class BanditTuner:
    """Light-weight multi-armed bandit tuner with exponential averaging."""

    def __init__(
        self,
        *,
        alpha: float = 0.3,
        exploration_bonus: float = 0.05,
    ) -> None:
        if not 0.0 < alpha <= 1.0:
            raise ValueError("alpha must be in (0, 1]")
        self._default = TuningConfig(alpha=float(alpha), exploration_bonus=max(0.0, float(exploration_bonus)))
        self._arms: Dict[str, Dict[str, ArmState]] = {}
        self._configs: Dict[str, TuningConfig] = {}
        self._lock = Lock()

    async def choose(self, binding: str, candidates: Iterable[str]) -> str:
        """Pick a flow arm for ``binding`` from ``candidates``."""

        async with self._lock:
            arms = self._arms.setdefault(binding, {})
            cfg = self._configs.setdefault(binding, self._default.clone())
            ordered: List[str] = []
            for flow in candidates:
                ordered.append(flow)
                arms.setdefault(flow, ArmState())
            unseen = [flow for flow in ordered if arms[flow].pulls == 0]
            if unseen:
                choice = unseen[0]
            else:
                choice = max(
                    ordered,
                    key=lambda flow: arms[flow].score + self._exploration_term(arms[flow], cfg.exploration_bonus),
                )
            arms[choice].pulls += 1
            return choice

    async def update(self, binding: str, flow: str, reward: float) -> None:
        async with self._lock:
            arms = self._arms.setdefault(binding, {})
            cfg = self._configs.setdefault(binding, self._default.clone())
            arm = arms.setdefault(flow, ArmState())
            arm.apply_reward(reward, cfg.alpha)

    async def configure(
        self,
        binding: str,
        params: Dict[str, Any],
        *,
        version: str,
        source: str = "remote",
    ) -> TuningConfig:
        async with self._lock:
            current = self._configs.get(binding, self._default.clone())
            alpha = params.get("alpha", current.alpha)
            bonus = params.get("exploration_bonus", current.exploration_bonus)
            if not 0.0 < float(alpha) <= 1.0:
                raise ValueError("alpha must be in (0, 1]")
            if float(bonus) < 0.0:
                raise ValueError("exploration_bonus must be >= 0")
            updated = TuningConfig(alpha=float(alpha), exploration_bonus=float(bonus), version=version, source=source)
            self._configs[binding] = updated
            return updated

    async def config(self, binding: str) -> TuningConfig:
        async with self._lock:
            cfg = self._configs.get(binding)
            if cfg is None:
                cfg = self._default.clone()
                self._configs[binding] = cfg
            return cfg.clone()

    async def stats(self, binding: str) -> Dict[str, Dict[str, float]]:
        async with self._lock:
            arms = self._arms.get(binding, {})
            cfg = self._configs.get(binding, self._default)
            report = {
                flow: {
                    "score": state.score,
                    "pulls": float(state.pulls),
                    "updates": float(state.updates),
                    "avg_reward": (state.total_reward / state.updates) if state.updates else 0.0,
                }
                for flow, state in arms.items()
            }
            report["__config"] = {
                "alpha": cfg.alpha,
                "exploration_bonus": cfg.exploration_bonus,
                "version": cfg.version,
                "source": cfg.source,
            }
            return report

    def _exploration_term(self, arm: ArmState, bonus: float) -> float:
        if bonus <= 0.0:
            return 0.0
        return bonus / math.sqrt(max(1.0, float(arm.pulls)))



def propose(observation: Observation, current_policy: Dict[str, Any]) -> Optional[Proposal]:
    """Generate a basic Proposal based on metric thresholds."""

    pending = observation.counter("flows_deferred_pending()", 0.0)
    total_errors = observation.counter("pipeline_steps_total(('status', 'error'),)", 0.0)

    changes = []
    summary_lines = []

    if pending > 5:
        changes.append(Change(path="flow.delay", value=min(current_policy.get("flow", {}).get("delay", 10) + 1, 30)))
        summary_lines.append(f"Increase flow delay due to {pending} pending deferred flows")

    if total_errors > 0:
        changes.append(Change(path="pipeline.auto_pause", value=True))
        summary_lines.append(f"Enable pipeline auto_pause after {total_errors} errors")

    if not changes:
        return None

    summary = "; ".join(summary_lines)
    proposal = Proposal(
        proposal_id="auto-tune",
        title="Automated policy adjustment",
        summary=summary,
        changes=changes,
    )
    return proposal


__all__ = ["BanditTuner", "TuningConfig", "propose"]
