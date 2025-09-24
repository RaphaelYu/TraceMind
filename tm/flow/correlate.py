from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple
from uuid import uuid4


@dataclass
class CorrelationHub:
    """In-memory token registry and signal store for deferred flow executions."""

    _pending: Dict[str, Tuple[str, dict]] = field(default_factory=dict)
    _signals: Dict[str, dict] = field(default_factory=dict)

    def reserve(self, flow_name: str, payload: Optional[dict] = None) -> str:
        token = uuid4().hex
        self._pending[token] = (flow_name, dict(payload or {}))
        return token

    def signal(self, req_id: str, payload: dict) -> None:
        self._signals[req_id] = dict(payload)

    def poll(self, req_id: str) -> Optional[dict]:
        payload = self._signals.get(req_id)
        return None if payload is None else dict(payload)

    def consume_signal(self, req_id: str) -> Optional[dict]:
        payload = self._signals.pop(req_id, None)
        return None if payload is None else dict(payload)

    def resolve(self, token: str) -> Optional[Tuple[str, dict]]:
        return self._pending.get(token)

    def consume(self, token: str) -> Optional[Tuple[str, dict]]:
        return self._pending.pop(token, None)
