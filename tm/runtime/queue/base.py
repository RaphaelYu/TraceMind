from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence


@dataclass(frozen=True)
class LeasedTask:
    """Container returned by the queue when leasing work."""

    offset: int
    task: Mapping[str, Any]
    lease_deadline: float
    token: str


class WorkQueue(abc.ABC):
    """Abstract base class for queue implementations used by the worker runtime."""

    @abc.abstractmethod
    def put(self, task: Mapping[str, Any]) -> int:
        """Enqueue *task* and return its monotonic offset."""

    @abc.abstractmethod
    def lease(self, count: int, lease_ms: int) -> Sequence[LeasedTask]:
        """Lease up to *count* tasks for *lease_ms* milliseconds."""

    @abc.abstractmethod
    def ack(self, offset: int, token: str) -> None:
        """Acknowledge the task identified by *offset* for the active lease *token*."""

    @abc.abstractmethod
    def nack(self, offset: int, token: str, *, requeue: bool = True) -> None:
        """Reject the task, optionally requeueing it for another consumer."""

    @abc.abstractmethod
    def reschedule(self, offset: int, *, available_at: float) -> None:
        """Update the availability time for a queued task."""

    @abc.abstractmethod
    def pending_count(self) -> int:
        """Return the number of tasks persisted but not acknowledged."""

    @abc.abstractmethod
    def oldest_available_at(self) -> Optional[float]:
        """Return the earliest availability time for pending tasks (monotonic)."""

    @abc.abstractmethod
    def flush(self) -> None:
        """Flush durable state to disk. No-op for in-memory queues."""

    @abc.abstractmethod
    def close(self) -> None:
        """Release any resources held by the queue."""

    def checkpoint(self) -> None:
        """Optional hook for graceful drain implementations."""
        self.flush()
