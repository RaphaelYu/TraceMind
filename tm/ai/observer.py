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
    counter_values: dict[str, float] = {}
    gauge_values: dict[str, float] = {}

    counters_blob = snapshot.get("counters")
    if isinstance(counters_blob, dict):
        for name, samples in counters_blob.items():
            if isinstance(samples, list):
                for labels, value in samples:
                    try:
                        key = f"{name}{labels}"
                        counter_values[key] = float(value)
                    except Exception:
                        continue

    gauges_blob = snapshot.get("gauges")
    if isinstance(gauges_blob, dict):
        for name, samples in gauges_blob.items():
            if isinstance(samples, list):
                for labels, value in samples:
                    try:
                        key = f"{name}{labels}"
                        gauge_values[key] = float(value)
                    except Exception:
                        continue
    return Observation(counters=counter_values, gauges=gauge_values)
