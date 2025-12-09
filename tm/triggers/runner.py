from __future__ import annotations

import asyncio
import signal
from contextlib import suppress

from .config import TriggerConfigSet, load_trigger_config
from .manager import TriggerManager
from .queue import TriggerQueueDispatcher
from typing import Callable


class TriggerRuntime:
    """High-level runtime that owns dispatcher + manager."""

    def __init__(
        self,
        config: TriggerConfigSet,
        *,
        queue_dir: str,
        idempotency_dir: str,
        dlq_dir: str,
    ) -> None:
        self._dispatcher = TriggerQueueDispatcher(
            queue_dir=queue_dir,
            idempotency_dir=idempotency_dir,
            dlq_dir=dlq_dir,
        )
        self._manager = TriggerManager(config, self._dispatcher.handle)
        self._stop_event = asyncio.Event()

    def request_stop(self) -> None:
        self._stop_event.set()

    async def run(self) -> None:
        try:
            await self._manager.run(self._stop_event)
        finally:
            self._dispatcher.close()


def run_triggers(
    *,
    config_path: str,
    queue_dir: str,
    idempotency_dir: str,
    dlq_dir: str,
) -> None:
    config = load_trigger_config(config_path)
    runtime = TriggerRuntime(
        config,
        queue_dir=queue_dir,
        idempotency_dir=idempotency_dir,
        dlq_dir=dlq_dir,
    )

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def _signal_handler(*_args) -> None:  # pragma: no cover - relies on OS signals
        runtime.request_stop()

    _install_signal_handlers(runtime.request_stop)

    try:
        loop.run_until_complete(runtime.run())
    finally:
        with suppress(Exception):
            loop.run_until_complete(loop.shutdown_asyncgens())
        asyncio.set_event_loop(None)
        loop.close()


def _install_signal_handlers(stop: Callable[[], None]) -> None:
    for sig_name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, sig_name, None)
        if sig is None:  # pragma: no cover - platform specific
            continue
        try:
            signal.signal(sig, lambda *_: stop())
        except (ValueError, OSError):  # pragma: no cover - unsupported in some contexts
            continue


__all__ = ["run_triggers", "TriggerRuntime"]
