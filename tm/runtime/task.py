from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping

EnvelopeDict = Dict[str, Any]
DEFAULT_HEADERS: Mapping[str, Any] = {}
DEFAULT_TRACE: Mapping[str, Any] = {}


@dataclass
class TaskEnvelope:
    """Schema for tasks persisted in the queue."""

    task_id: str
    flow_id: str
    input: Mapping[str, Any]
    headers: Mapping[str, Any] = field(default_factory=dict)
    attempt: int = 0
    scheduled_at: float = field(default_factory=lambda: time.time())
    trace: Mapping[str, Any] = field(default_factory=dict)

    @property
    def idempotency_key(self) -> str | None:
        value = self.headers.get("idempotency_key") if isinstance(self.headers, Mapping) else None
        if isinstance(value, str) and value:
            return value
        return None

    @property
    def composite_key(self) -> str:
        idem = self.idempotency_key
        return idem if idem else self.task_id

    def to_dict(self) -> EnvelopeDict:
        return {
            "task_id": self.task_id,
            "flow_id": self.flow_id,
            "input": _as_jsonable(self.input),
            "headers": _as_jsonable(self.headers),
            "attempt": int(self.attempt),
            "scheduled_at": float(self.scheduled_at),
            "trace": _as_jsonable(self.trace),
        }

    def with_retry(self, *, attempt: int, scheduled_at: float) -> "TaskEnvelope":
        return TaskEnvelope(
            task_id=self.task_id,
            flow_id=self.flow_id,
            input=self.input,
            headers=self.headers,
            attempt=attempt,
            scheduled_at=scheduled_at,
            trace=self.trace,
        )

    @classmethod
    def new(
        cls,
        *,
        flow_id: str,
        input: Mapping[str, Any],
        headers: Mapping[str, Any] | None = None,
        trace: Mapping[str, Any] | None = None,
        task_id: str | None = None,
        scheduled_at: float | None = None,
    ) -> "TaskEnvelope":
        task_id = task_id or uuid.uuid4().hex
        headers = dict(headers or {})
        if "task_id" in headers:
            headers.pop("task_id")
        scheduled_at = scheduled_at if scheduled_at is not None else time.time()
        return cls(
            task_id=task_id,
            flow_id=str(flow_id),
            input=_freeze_mapping(input),
            headers=_freeze_mapping(headers),
            attempt=0,
            scheduled_at=scheduled_at,
            trace=_freeze_mapping(trace or {}),
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TaskEnvelope":
        if not isinstance(payload, Mapping):
            raise TypeError("task payload must be a mapping")
        task_id = str(payload.get("task_id"))
        if not task_id:
            raise ValueError("task payload missing task_id")
        flow_id = str(payload.get("flow_id"))
        if not flow_id:
            raise ValueError("task payload missing flow_id")
        attempt = int(payload.get("attempt", 0))
        scheduled_at_raw = payload.get("scheduled_at")
        scheduled_at = float(scheduled_at_raw) if scheduled_at_raw is not None else time.time()
        headers = payload.get("headers")
        trace = payload.get("trace")
        return cls(
            task_id=task_id,
            flow_id=flow_id,
            input=_freeze_mapping(payload.get("input") or {}),
            headers=_freeze_mapping(headers or {}),
            attempt=attempt,
            scheduled_at=scheduled_at,
            trace=_freeze_mapping(trace or {}),
        )


def _freeze_mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    raise TypeError("expected mapping for task field")


def _as_jsonable(value: Mapping[str, Any]) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    return dict(value)


__all__ = ["TaskEnvelope"]
