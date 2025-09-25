"""Metric recorder that bridges domain events to the metrics registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Dict, Optional

from .counters import Registry, metrics


@dataclass
class Recorder:
    _registry: Registry = metrics
    _default: ClassVar[Optional["Recorder"]] = None

    @classmethod
    def default(cls) -> "Recorder":
        if cls._default is None:
            cls._default = cls()
        return cls._default

    # Flow events -----------------------------------------------------
    def on_flow_started(self, flow: str, model: str | None = None) -> None:
        labels = {"flow": flow}
        if model:
            labels["model"] = model
        self._registry.get_counter("flows_started_total").inc(labels=labels)

    def on_flow_finished(self, flow: str, model: str | None, status: str) -> None:
        labels = {"flow": flow, "status": status}
        if model:
            labels["model"] = model
        self._registry.get_counter("flows_finished_total").inc(labels=labels)

    def on_flow_pending(self, delta: int) -> None:
        gauge = self._registry.get_gauge("flows_deferred_pending")
        gauge.inc(value=float(delta))

    # Service events --------------------------------------------------
    def on_service_request(self, model: str, operation: str) -> None:
        self._registry.get_counter("service_requests_total").inc(labels={"model": model, "op": operation})

    # Pipeline events -------------------------------------------------
    def on_pipeline_step(self, rule: str, step: str, status: str) -> None:
        self._registry.get_counter("pipeline_steps_total").inc(labels={"rule": rule, "step": step, "status": status})
