from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple
from uuid import uuid4


@dataclass
class CorrelationHub:
    """In-memory token registry for deferred flow executions."""

    _pending: Dict[str, Tuple[str, dict]] = field(default_factory=dict)

    def reserve(self, flow_name: str, payload: Optional[dict] = None) -> str:
        token = uuid4().hex
        self._pending[token] = (flow_name, dict(payload or {}))
        return token

    def resolve(self, token: str) -> Optional[Tuple[str, dict]]:
        return self._pending.get(token)

    def consume(self, token: str) -> Optional[Tuple[str, dict]]:
        return self._pending.pop(token, None)
