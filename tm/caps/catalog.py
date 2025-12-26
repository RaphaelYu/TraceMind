from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping

from tm.artifacts import validate_capability_spec


class CapabilityCatalogError(RuntimeError):
    """Base error for capability catalog operations."""


class CapabilityAlreadyExists(CapabilityCatalogError):
    """Raised when registering a capability that already exists without overwrite."""


class CapabilityNotFound(CapabilityCatalogError):
    """Raised when querying a missing capability."""


DEFAULT_CATALOG_PATH = Path.home() / ".trace-mind" / "capabilities.json"


@dataclass(frozen=True)
class CatalogEntry:
    capability_id: str
    spec: Mapping[str, Any]


class CapabilityCatalog:
    """Simple capability catalog backed by a JSON file."""

    def __init__(self, *, path: Path | str | None = None) -> None:
        self._path = Path(path) if path else DEFAULT_CATALOG_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def register(self, spec: Mapping[str, Any], *, overwrite: bool = False) -> CatalogEntry:
        """Register a capability spec after schema validation."""
        validate_capability_spec(spec)
        data = self._load()
        capability_id = str(spec["capability_id"])
        if capability_id in data and not overwrite:
            raise CapabilityAlreadyExists(f"capability '{capability_id}' already registered")
        data[capability_id] = spec
        self._persist(data)
        return CatalogEntry(capability_id=capability_id, spec=spec)

    def get(self, capability_id: str) -> Mapping[str, Any]:
        data = self._load()
        try:
            return data[capability_id]
        except KeyError as exc:
            raise CapabilityNotFound(capability_id) from exc

    def list(self) -> list[CatalogEntry]:
        data = self._load()
        return [CatalogEntry(capability_id=k, spec=v) for k, v in sorted(data.items())]

    def exists(self, capability_id: str) -> bool:
        return capability_id in self._load()

    def _load(self) -> Dict[str, Mapping[str, Any]]:
        if not self._path.exists():
            return {}
        try:
            with self._path.open("r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except json.JSONDecodeError:
            return {}
        if not isinstance(payload, Mapping):
            return {}
        return {str(k): v for k, v in payload.items() if isinstance(k, str)}

    def _persist(self, data: Mapping[str, Mapping[str, Any]]) -> None:
        serialized = {k: v for k, v in data.items()}
        with self._path.open("w", encoding="utf-8") as fh:
            json.dump(serialized, fh, indent=2, ensure_ascii=False)


__all__ = [
    "CapabilityCatalog",
    "CapabilityCatalogError",
    "CapabilityAlreadyExists",
    "CapabilityNotFound",
    "CatalogEntry",
]
