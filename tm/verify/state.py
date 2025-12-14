from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, Tuple


def _normalize(value: Any) -> Any:
    """Recursively normalize mappings/sequences for stable hashing."""
    if isinstance(value, Mapping):
        return {k: _normalize(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_normalize(v) for v in value]
    return value


@dataclass(frozen=True)
class State:
    store: Mapping[str, Any]
    pending: Tuple[str, ...]
    done: Tuple[str, ...]
    events: Tuple[str, ...]

    def stable_hash(self, mode: str = "full") -> str:
        """Compute a deterministic hash of this state."""
        if mode not in {"full", "store"}:
            raise ValueError(f"Unknown hash mode '{mode}'")
        payload: dict[str, Any] = {"store": _normalize(self.store)}
        if mode == "full":
            payload["pending"] = list(self.pending)
            payload["done"] = list(self.done)
            payload["events"] = list(self.events)
        raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        return {
            "store": dict(self.store),
            "pending": list(self.pending),
            "done": list(self.done),
            "events": list(self.events),
        }
