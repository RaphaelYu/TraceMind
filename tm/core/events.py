from dataclasses import dataclass
from typing import Dict, Any


@dataclass(frozen=True)
class Event:
    pass


@dataclass(frozen=True)
class ObjectUpserted(Event):
    kind: str
    obj_id: str
    payload: Dict[str, Any]
    txn_meta: Dict[str, Any] | None = None
