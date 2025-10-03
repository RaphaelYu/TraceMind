from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from tm.obs.counters import Registry
from tm.obs import counters


@dataclass(frozen=True)
class Observation:
    counters: Dict[str, float]
    gauges: Dict[str, float]

    def counter(self, name: str, default: float = 0.0) -> float:
        return self.counters.get(name, default)

    def gauge(self, name: str, default: float = 0.0) -> float:
        return self.gauges.get(name, default)


def from_metrics(registry: Registry | None = None) -> Observation:
    reg = registry or counters.metrics
    snapshot = reg.snapshot()
    counters = {
        f"{name}{labels}": value
        for name, samples in snapshot.get("counters", {}).items()
        for labels, value in samples
    }
    gauges = {
        f"{name}{labels}": value
        for name, samples in snapshot.get("gauges", {}).items()
        for labels, value in samples
    }
    return Observation(counters=counters, gauges=gauges)
