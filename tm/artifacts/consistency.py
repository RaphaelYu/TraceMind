from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Mapping, Sequence

from .diff import diff_artifacts
from .models import Artifact, load_yaml_artifact
from .registry import ArtifactRegistry, RegistryEntry


class ConsistencyCode:
    C1 = "C1"
    C2 = "C2"
    C3 = "C3"


@dataclass
class ConsistencyIssue:
    code: str
    severity: str
    summary: str
    details: Mapping[str, Any]

    def machine_readable(self) -> Mapping[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "summary": self.summary,
            "details": dict(self.details),
        }


@dataclass
class ConsistencyReport:
    artifact_id: str
    issues: List[ConsistencyIssue] = field(default_factory=list)

    @property
    def human_summary(self) -> str:
        if not self.issues:
            return "no consistency issues detected"
        return "; ".join(issue.summary for issue in self.issues)

    @property
    def machine_readable(self) -> List[Mapping[str, Any]]:
        return [issue.machine_readable() for issue in self.issues]


def _load_previous_artifact(entry: RegistryEntry) -> Artifact | None:
    path = Path(entry.path)
    if not path.exists():
        return None
    try:
        return load_yaml_artifact(path)
    except Exception:
        return None


def _calc_intent_entries(artifact: Artifact, registry: ArtifactRegistry) -> Sequence[RegistryEntry]:
    intent_id = getattr(artifact.body, "intent_id", None)
    if not intent_id:
        return []
    return registry.list_by_intent_id(intent_id)


def _check_C1(artifact: Artifact, registry: ArtifactRegistry) -> List[ConsistencyIssue]:
    issues: List[ConsistencyIssue] = []
    for entry in _calc_intent_entries(artifact, registry):
        if entry.body_hash == artifact.envelope.body_hash:
            continue
        previous = _load_previous_artifact(entry)
        if previous is None:
            continue
        diff = diff_artifacts(artifact, previous)
        message = f"C1: intent {entry.intent_id or entry.artifact_id} body changed in canonical representation"
        issues.append(
            ConsistencyIssue(
                code=ConsistencyCode.C1,
                severity="error",
                summary=message,
                details=diff.machine_readable(),
            )
        )
    return issues


def _check_C2(artifact: Artifact, registry: ArtifactRegistry) -> List[ConsistencyIssue]:
    issues: List[ConsistencyIssue] = []
    derived_from = artifact.envelope.meta.get("derived_from") or {}
    if not isinstance(derived_from, Mapping):
        return issues
    intent_hash = derived_from.get("intent_body_hash")
    if not intent_hash:
        return issues
    related = [
        entry
        for entry in registry.list_all()
        if entry.meta.get("derived_from", {}).get("intent_body_hash") == intent_hash
    ]
    for entry in related:
        if entry.body_hash == artifact.envelope.body_hash:
            continue
        if artifact.envelope.meta.get("provenance_explanation"):
            continue
        summary = f"C2: derived artifact {artifact.envelope.artifact_id} body hash moved without explanation"
        issues.append(
            ConsistencyIssue(
                code=ConsistencyCode.C2,
                severity="warning",
                summary=summary,
                details={
                    "intent_body_hash": intent_hash,
                    "previous_artifact_id": entry.artifact_id,
                    "previous_body_hash": entry.body_hash,
                    "current_body_hash": artifact.envelope.body_hash,
                },
            )
        )
    return issues


def _check_C3(artifact: Artifact, registry: ArtifactRegistry) -> List[ConsistencyIssue]:
    issues: List[ConsistencyIssue] = []
    current_inv = artifact.envelope.meta.get("invariant_status", {})
    if not isinstance(current_inv, Mapping):
        return issues
    intent_entries = _calc_intent_entries(artifact, registry)
    for entry in intent_entries:
        previous_inv = entry.meta.get("invariant_status", {})
        if not isinstance(previous_inv, Mapping):
            continue
        regressions = [name for name, passed in previous_inv.items() if passed and not current_inv.get(name, False)]
        if not regressions:
            continue
        summary = f"C3: artifact {artifact.envelope.artifact_id} regresses invariants: {', '.join(regressions)}"
        issues.append(
            ConsistencyIssue(
                code=ConsistencyCode.C3,
                severity="error",
                summary=summary,
                details={"regressions": regressions, "previous_artifact_id": entry.artifact_id},
            )
        )
    return issues


def check_consistency(artifact: Artifact, registry: ArtifactRegistry) -> ConsistencyReport:
    issues: List[ConsistencyIssue] = []
    issues.extend(_check_C1(artifact, registry))
    issues.extend(_check_C2(artifact, registry))
    issues.extend(_check_C3(artifact, registry))
    return ConsistencyReport(artifact_id=artifact.envelope.artifact_id, issues=issues)
