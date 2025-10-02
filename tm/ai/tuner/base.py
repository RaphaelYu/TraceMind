from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Mapping, Optional


@dataclass(frozen=True)
class ArmSnapshot:
    pulls: int
    total_reward: float
    avg_reward: float


class TunerStrategy(ABC):
    """Abstract interface for online arm selection strategies."""

    @abstractmethod
    def select(
        self,
        flow_id: str,
        policy_id: str,
        arms: Mapping[str, Mapping[str, object]] | Mapping[str, object],
        ctx: Optional[Mapping[str, object]] = None,
    ) -> str:
        """Pick an arm identifier from ``arms`` for ``flow_id``/``policy_id``."""

    @abstractmethod
    def update(self, flow_id: str, policy_id: str, arm_id: str, reward: float) -> None:
        """Persist reward feedback for an arm."""

    def stats(self, flow_id: str, policy_id: str) -> Dict[str, ArmSnapshot]:
        """Optional hook returning arm statistics for diagnostics."""

        return {}


__all__ = ["TunerStrategy", "ArmSnapshot"]
