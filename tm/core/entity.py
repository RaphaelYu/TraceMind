# tm/core/entity.py
from dataclasses import dataclass
from typing import Dict, Any


@dataclass(frozen=True)
class EntityKey:
    kind: str
    id: str


class EntityMapper:
    """Maps domain-specific payloads to canonical events/commands."""

    def to_events(self, key: EntityKey, command: Dict[str, Any]) -> list[dict]:
        # minimal default mapping; domain adapters can subclass/override
        return [{"etype": "ObjectUpserted", "key": f"{key.kind}:{key.id}", "payload": command}]
