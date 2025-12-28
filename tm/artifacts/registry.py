from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Union

from .models import Artifact, ArtifactStatus, ArtifactType
from .storage import RegistryStorage

DEFAULT_REGISTRY_PATH = Path(".tracemind/registry.jsonl")


@dataclass
class RegistryEntry:
    artifact_id: str
    artifact_type: ArtifactType
    body_hash: str
    path: str
    meta: Mapping[str, Any]
    version: str
    created_at: str
    status: ArtifactStatus
    intent_id: str | None = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type.value,
            "body_hash": self.body_hash,
            "path": self.path,
            "meta": dict(self.meta),
            "version": self.version,
            "created_at": self.created_at,
            "status": self.status.value,
            "intent_id": self.intent_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RegistryEntry":
        return cls(
            artifact_id=str(data["artifact_id"]),
            artifact_type=ArtifactType(str(data["artifact_type"])),
            body_hash=str(data["body_hash"]),
            path=str(data["path"]),
            meta=data.get("meta", {}) or {},
            version=str(data["version"]),
            created_at=str(data["created_at"]),
            status=ArtifactStatus(str(data["status"])),
            intent_id=data.get("intent_id"),
        )

    @classmethod
    def from_artifact(cls, artifact: Artifact, artifact_path: Union[Path, str]) -> "RegistryEntry":
        intent_id = getattr(artifact.body, "intent_id", None)
        return cls(
            artifact_id=artifact.envelope.artifact_id,
            artifact_type=artifact.envelope.artifact_type,
            body_hash=artifact.envelope.body_hash,
            path=str(artifact_path),
            meta=dict(artifact.envelope.meta),
            version=artifact.envelope.version,
            created_at=artifact.envelope.created_at,
            status=artifact.envelope.status,
            intent_id=intent_id if isinstance(intent_id, str) else None,
        )


class ArtifactRegistry:
    def __init__(self, storage: RegistryStorage | None = None):
        self.storage = storage or RegistryStorage(DEFAULT_REGISTRY_PATH)

    def _iter_entries(self) -> Iterable[RegistryEntry]:
        for record in self.storage.read_records():
            yield RegistryEntry.from_dict(record)

    def list_all(self) -> List[RegistryEntry]:
        return list(self._iter_entries())

    def get_by_artifact_id(self, artifact_id: str) -> RegistryEntry | None:
        for entry in self._iter_entries():
            if entry.artifact_id == artifact_id:
                return entry
        return None

    def list_by_intent_id(self, intent_id: str) -> List[RegistryEntry]:
        return [entry for entry in self._iter_entries() if entry.intent_id == intent_id]

    def list_by_type(self, artifact_type: ArtifactType | str) -> List[RegistryEntry]:
        target_type = ArtifactType(artifact_type) if isinstance(artifact_type, str) else artifact_type
        return [entry for entry in self._iter_entries() if entry.artifact_type == target_type]

    def list_by_body_hash(self, body_hash: str) -> List[RegistryEntry]:
        return [entry for entry in self._iter_entries() if entry.body_hash == body_hash]

    def add(self, artifact: Artifact, artifact_path: Union[Path, str]) -> RegistryEntry:
        if artifact.envelope.status != ArtifactStatus.ACCEPTED:
            raise ValueError("only accepted artifacts may be registered")
        entry = RegistryEntry.from_artifact(artifact, artifact_path)
        self.storage.append(entry.to_dict())
        return entry


def default_registry() -> ArtifactRegistry:
    return ArtifactRegistry()


__all__ = ["ArtifactRegistry", "RegistryEntry", "default_registry"]
