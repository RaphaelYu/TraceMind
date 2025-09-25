"""Demonstrate custom metrics and exporters."""

from __future__ import annotations

from typing import Mapping

from tm.obs.counters import counter, metrics
from tm.obs.exporters import Exporter, register_exporter
from tm.obs.counters import Registry


class PrintExporter:
    """Minimal exporter that prints every snapshot."""

    def __init__(self) -> None:
        self._started = False

    def start(self, registry: Registry) -> None:
        self._started = True
        print("PrintExporter started with", len(registry.snapshot().get("counters", {})), "counters")

    def stop(self) -> None:
        self._started = False

    def export(self, snapshot: Mapping[str, object]) -> None:
        if self._started:
            print("Snapshot:", snapshot)


register_exporter("print", lambda registry: PrintExporter())


events_total = counter("events_total", ["kind"])

if __name__ == "__main__":
    events_total(kind="demo")
    print("Current snapshot:", metrics.snapshot())
