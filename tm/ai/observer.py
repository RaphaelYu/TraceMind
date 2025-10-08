from __future__ import annotations

from dataclasses import dataclass

from tm.obs import counters
from tm.obs.counters import Registry


@dataclass(frozen=True)
class Observation:
    counters: dict[str, float]
    gauges: dict[str, float]

    def counter(self, name: str, default: float = 0.0) -> float:
        return self.counters.get(name, default)

    def gauge(self, name: str, default: float = 0.0) -> float:
        return self.gauges.get(name, default)


def from_metrics(registry: Registry | None = None) -> Observation:
    reg = registry or counters.metrics
    snapshot = reg.snapshot()
    counter_values = {
        f"{name}{labels}": value for name, samples in snapshot.get("counters", {}).items() for labels, value in samples
    }
    gauge_values = {
        f"{name}{labels}": value for name, samples in snapshot.get("gauges", {}).items() for labels, value in samples
    }
    return Observation(counters=counter_values, gauges=gauge_values)
