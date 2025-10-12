from __future__ import annotations

import asyncio
from pathlib import Path

from tm.runtime.dlq import DeadLetterStore
from tm.runtime.idempotency import IdempotencyStore
from tm.runtime.queue import FileWorkQueue
from tm.runtime.queue.manager import TaskQueueManager

from .manager import TriggerEvent


class TriggerQueueDispatcher:
    """Dispatches trigger events into the TraceMind work queue."""

    def __init__(
        self,
        *,
        queue_dir: str,
        idempotency_dir: str,
        dlq_dir: str,
    ) -> None:
        Path(queue_dir).mkdir(parents=True, exist_ok=True)
        Path(idempotency_dir).mkdir(parents=True, exist_ok=True)
        Path(dlq_dir).mkdir(parents=True, exist_ok=True)
        self._queue = FileWorkQueue(queue_dir)
        self._idempotency = IdempotencyStore(dir_path=idempotency_dir)
        self._dlq = DeadLetterStore(dlq_dir)
        self._manager = TaskQueueManager(self._queue, self._idempotency, dead_letters=self._dlq)

    async def handle(self, event: TriggerEvent) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._enqueue_sync, event)

    def _enqueue_sync(self, event: TriggerEvent) -> None:
        headers = dict(event.headers)
        payload = dict(event.payload)
        if event.idempotency_key:
            headers.setdefault("idempotency_key", event.idempotency_key)
        outcome = self._manager.enqueue(
            flow_id=event.flow_id,
            input=payload,
            headers=headers or None,
            trace=None,
        )
        if outcome.cached_result is not None:
            return

    def close(self) -> None:
        self._queue.flush()
        self._queue.close()
