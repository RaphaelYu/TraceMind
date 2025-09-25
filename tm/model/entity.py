"""Model entities backed by ModelSpec definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from .spec import ModelSpec


@dataclass(frozen=True)
class Entity:
    spec: ModelSpec
    identity: str
    attributes: Dict[str, Any]
    meta: Optional[Dict[str, Any]] = None
    partial: bool = False

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "model": self.spec.name,
            "id": self.identity,
            "attributes": dict(self.attributes),
        }
        if self.meta is not None:
            data["meta"] = dict(self.meta)
        if self.partial:
            data["partial"] = True
        return data
