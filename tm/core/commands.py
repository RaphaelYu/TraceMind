from dataclasses import dataclass
from typing import Dict, Any


@dataclass(frozen=True)
class Command:
    pass


@dataclass(frozen=True)
class UpsertObject(Command):
    kind: str
    obj_id: str
    payload: Dict[str, Any]
    txn_meta: Dict[str, Any] | None = None
