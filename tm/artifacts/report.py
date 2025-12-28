from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ArtifactVerificationReport:
    artifact_id: str
    success: bool = False
    errors: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def add_error(self, message: str) -> None:
        self.errors.append(message)
        self.success = False

    def mark_success(self) -> None:
        self.success = True

    def as_dict(self) -> Dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "success": self.success,
            "errors": list(self.errors),
            "details": dict(self.details),
        }
