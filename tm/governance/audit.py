"""Append-only audit trail with masking support."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Mapping

from .config import AuditConfig


class AuditTrail:
    def __init__(self, config: AuditConfig) -> None:
        self._enabled = config.enabled
        self._path = Path(config.path)
        self._mask_fields = tuple(config.mask_fields or ())
        self._lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def record_async(self, event_type: str, payload: Mapping[str, Any]) -> None:
        if not self._enabled:
            return
        entry = self._prepare_entry(event_type, payload)
        await self._write_async(entry)

    def record(self, event_type: str, payload: Mapping[str, Any]) -> None:
        if not self._enabled:
            return
        entry = self._prepare_entry(event_type, payload)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self._write_sync(entry)
        else:
            loop.create_task(self._write_async(entry))

    def _prepare_entry(self, event_type: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        masked = _mask_payload(payload, self._mask_fields)
        return {
            "ts": time.time(),
            "type": event_type,
            "payload": masked,
        }

    async def _write_async(self, entry: Mapping[str, Any]) -> None:
        async with self._lock:
            await asyncio.to_thread(self._write_sync, entry)

    def _write_sync(self, entry: Mapping[str, Any]) -> None:
        path = self._path
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False))
            fh.write("\n")


def _mask_payload(value: Any, mask_fields: tuple[str, ...]) -> Any:
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            if key in mask_fields:
                result[key] = _mask_value(item)
            else:
                result[key] = _mask_payload(item, mask_fields)
        return result
    if isinstance(value, list):
        return [_mask_payload(item, mask_fields) for item in value]
    return value


def _mask_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return {k: _mask_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_mask_value(v) for v in value]
    if isinstance(value, (str, bytes)):
        return "***"
    if isinstance(value, int):
        return 0
    if isinstance(value, float):
        return 0.0
    return "***"


__all__ = ["AuditTrail"]
