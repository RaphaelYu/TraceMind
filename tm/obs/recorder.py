"""Metric recorder that bridges domain events to the metrics registry."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import ClassVar, Optional

from .counters import Registry
from . import counters
from tm.kstore import DEFAULT_KSTORE_URL, KStore, open_kstore


@dataclass
class Recorder:
    _registry: Registry = counters.metrics
    _kstore: KStore | None = field(default=None, repr=False)
    _default: ClassVar[Optional["Recorder"]] = None

    @classmethod
    def default(cls) -> "Recorder":
        if cls._default is None:
            cls._default = cls()
        return cls._default

    def __post_init__(self) -> None:
        if self._kstore is None:
            url = os.getenv("TM_KSTORE", DEFAULT_KSTORE_URL)
            self._kstore = open_kstore(url)

    @property
    def kstore(self) -> KStore:
        if self._kstore is None:
            raise RuntimeError("recorder knowledge store is not available")
        return self._kstore

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

    def on_guard_block(self, rule: str, flow: str) -> None:
        labels = {"rule": rule, "flow": flow}
        self._registry.get_counter("tm_audit_guard_blocked_total").inc(labels=labels)

    def on_flow_pending(self, delta: int) -> None:
        gauge = self._registry.get_gauge("flows_deferred_pending")
        gauge.inc(value=float(delta))

    # Service events --------------------------------------------------
    def on_service_request(self, model: str, operation: str) -> None:
        self._registry.get_counter("service_requests_total").inc(labels={"model": model, "op": operation})

    # Pipeline events -------------------------------------------------
    def on_pipeline_step(self, rule: str, step: str, status: str) -> None:
        self._registry.get_counter("pipeline_steps_total").inc(labels={"rule": rule, "step": step, "status": status})

    # Policy/tuner events ----------------------------------------------
    def on_tuner_select(self, binding: str, arm: str) -> None:
        if not binding or not arm:
            return
        # Selection counter is recorded directly inside the tuner implementation.
        return None

    def on_tuner_reward(self, binding: str, arm: str, reward: float) -> None:
        if not binding or not arm:
            return
        labels = {"flow": binding, "arm": arm}
        self._registry.get_gauge("tm_tuner_reward_sum").inc(value=float(reward), labels=labels)

    # Planner events ----------------------------------------------------
    def on_plan_result(
        self,
        *,
        provider: str,
        model: str,
        duration_ms: float,
        steps: int,
        retries: int,
        tokens_in: int | float | None,
        tokens_out: int | float | None,
        cost_usd: float | None,
        status: str,
    ) -> None:
        labels = {
            "provider": provider or "unknown",
            "model": model or "unknown",
        }
        self._registry.get_counter("tm_plan_requests_total").inc(labels=labels)
        if status != "ok":
            self._registry.get_counter("tm_plan_failures_total").inc(labels=labels)
        self._registry.get_counter("tm_plan_steps_executed_total").inc(value=float(max(0, steps)), labels=labels)
        if retries:
            self._registry.get_counter("tm_plan_retries_total").inc(value=float(retries), labels=labels)
        self._registry.get_gauge("tm_plan_last_duration_ms").set(float(max(0.0, duration_ms)), labels=labels)

    def on_reflect_result(
        self,
        *,
        provider: str,
        model: str,
        duration_ms: float,
        status: str,
    ) -> None:
        labels = {
            "provider": provider or "unknown",
            "model": model or "unknown",
        }
        self._registry.get_counter("tm_reflect_requests_total").inc(labels=labels)
        if status != "ok":
            self._registry.get_counter("tm_reflect_failures_total").inc(labels=labels)
        self._registry.get_gauge("tm_reflect_last_duration_ms").set(float(max(0.0, duration_ms)), labels=labels)
