from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Dict, List, Mapping, Sequence

from tm.artifacts.types import ArtifactType


def _require_field(data: Mapping[str, Any], key: str) -> Any:
    if key not in data or data[key] is None:
        raise ValueError(f"missing required field: '{key}'")
    return data[key]


def _ensure_dict(value: Any, name: str) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping")
    return dict(value)


def _ensure_str(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    return value


def _force_sequence(value: Any, name: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise TypeError(f"{name} must be a sequence")
    return value


def _force_list(value: Any, name: str) -> List[Any]:
    seq = _force_sequence(value, name)
    return [item for item in seq]


def _force_str_list(value: Any, name: str) -> List[str]:
    if value is None:
        return []
    seq = _force_sequence(value, name)
    return [_ensure_str(item, f"{name} item") for item in seq]


def _ensure_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{name} must be a boolean")
    return value


@dataclass
class EnvSnapshotBody:
    artifact_type: ClassVar[ArtifactType] = ArtifactType.ENVIRONMENT_SNAPSHOT
    snapshot_id: str
    timestamp: str
    environment: Dict[str, Any]
    constraints: List[Dict[str, Any]]
    data_hash: str

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "EnvSnapshotBody":
        constraints_raw = data.get("constraints") or []
        if constraints_raw is None:
            constraints_raw = []
        constraints_seq = _force_sequence(constraints_raw, "constraints")
        constraints = [_ensure_dict(item, "constraint") for item in constraints_seq]
        return cls(
            snapshot_id=_ensure_str(_require_field(data, "snapshot_id"), "snapshot_id"),
            timestamp=_ensure_str(_require_field(data, "timestamp"), "timestamp"),
            environment=_ensure_dict(_require_field(data, "environment"), "environment"),
            constraints=constraints,
            data_hash=_ensure_str(_require_field(data, "data_hash"), "data_hash"),
        )


@dataclass
class ProposedChangeDecision:
    effect_ref: str
    target_state: Dict[str, Any]
    idempotency_key: str
    reasoning_trace: str | None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ProposedChangeDecision":
        return cls(
            effect_ref=_ensure_str(_require_field(data, "effect_ref"), "decision.effect_ref"),
            target_state=_ensure_dict(_require_field(data, "target_state"), "decision.target_state"),
            idempotency_key=_ensure_str(_require_field(data, "idempotency_key"), "decision.idempotency_key"),
            reasoning_trace=(
                _ensure_str(data.get("reasoning_trace"), "decision.reasoning_trace")
                if data.get("reasoning_trace") is not None
                else None
            ),
        )


@dataclass
class LlmMetadata:
    model: str
    prompt_hash: str
    determinism_hint: str
    model_id: str | None = None
    model_version: str | None = None
    prompt_template_version: str | None = None
    prompt_version: str | None = None
    config_id: str | None = None
    inputs_hash: str | None = None

    OPTIONS = {"deterministic", "replayable", "heuristic"}

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "LlmMetadata":
        hint = _ensure_str(_require_field(data, "determinism_hint"), "llm_metadata.determinism_hint")
        if hint not in cls.OPTIONS:
            raise ValueError("llm_metadata.determinism_hint must be one of: " + ", ".join(sorted(cls.OPTIONS)))
        model_id = data.get("model_id")
        model_version = data.get("model_version")
        prompt_template_version = data.get("prompt_template_version")
        prompt_version = data.get("prompt_version")
        config_id = data.get("config_id")
        inputs_hash = data.get("inputs_hash")
        return cls(
            model=_ensure_str(_require_field(data, "model"), "llm_metadata.model"),
            prompt_hash=_ensure_str(_require_field(data, "prompt_hash"), "llm_metadata.prompt_hash"),
            determinism_hint=hint,
            model_id=_ensure_str(model_id, "llm_metadata.model_id") if model_id is not None else None,
            model_version=(
                _ensure_str(model_version, "llm_metadata.model_version") if model_version is not None else None
            ),
            prompt_template_version=(
                _ensure_str(prompt_template_version, "llm_metadata.prompt_template_version")
                if prompt_template_version is not None
                else None
            ),
            prompt_version=(
                _ensure_str(prompt_version, "llm_metadata.prompt_version") if prompt_version is not None else None
            ),
            config_id=_ensure_str(config_id, "llm_metadata.config_id") if config_id is not None else None,
            inputs_hash=_ensure_str(inputs_hash, "llm_metadata.inputs_hash") if inputs_hash is not None else None,
        )


@dataclass
class ProposedChangePlanBody:
    artifact_type: ClassVar[ArtifactType] = ArtifactType.PROPOSED_CHANGE_PLAN
    plan_id: str
    intent_id: str
    decisions: List[ProposedChangeDecision]
    llm_metadata: LlmMetadata
    summary: str
    policy_requirements: List[str]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ProposedChangePlanBody":
        decisions_raw = data.get("decisions")
        if decisions_raw is None:
            raise ValueError("decisions field is required for ProposedChangePlan")
        if not isinstance(decisions_raw, Sequence) or isinstance(decisions_raw, str):
            raise TypeError("decisions must be a list of mappings")
        decisions = [ProposedChangeDecision.from_mapping(_ensure_dict(item, "decision")) for item in decisions_raw]
        llm_metadata_raw = _ensure_dict(_require_field(data, "llm_metadata"), "llm_metadata")
        policy_requirements = _force_str_list(data.get("policy_requirements"), "policy_requirements")
        return cls(
            plan_id=_ensure_str(_require_field(data, "plan_id"), "plan_id"),
            intent_id=_ensure_str(_require_field(data, "intent_id"), "intent_id"),
            decisions=decisions,
            llm_metadata=LlmMetadata.from_mapping(llm_metadata_raw),
            summary=_ensure_str(_require_field(data, "summary"), "summary"),
            policy_requirements=policy_requirements,
        )


@dataclass
class PolicyDecision:
    effect_ref: str
    allowed: bool
    reason: str

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "PolicyDecision":
        return cls(
            effect_ref=_ensure_str(_require_field(data, "effect_ref"), "policy_decision.effect_ref"),
            allowed=_ensure_bool(_require_field(data, "allowed"), "policy_decision.allowed"),
            reason=_ensure_str(_require_field(data, "reason"), "policy_decision.reason"),
        )


@dataclass
class ExecutionReportBody:
    artifact_type: ClassVar[ArtifactType] = ArtifactType.EXECUTION_REPORT
    report_id: str
    artifact_refs: Dict[str, Any]
    status: str
    policy_decisions: List[PolicyDecision]
    errors: List[str]
    artifacts: Dict[str, Mapping[str, Any]]
    execution_hash: str

    ALLOWED_STATUSES = {"succeeded", "partial", "failed"}

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ExecutionReportBody":
        artifact_refs = _ensure_dict(_require_field(data, "artifact_refs"), "artifact_refs")
        artifacts_raw = _ensure_dict(_require_field(data, "artifacts"), "artifacts")
        policy_decisions_raw = data.get("policy_decisions") or []
        if policy_decisions_raw is None:
            policy_decisions_raw = []
        if not isinstance(policy_decisions_raw, Sequence) or isinstance(policy_decisions_raw, str):
            raise TypeError("policy_decisions must be a list of mappings")
        decisions = [
            PolicyDecision.from_mapping(_ensure_dict(item, "policy_decision")) for item in policy_decisions_raw
        ]
        status = _ensure_str(_require_field(data, "status"), "status")
        if status not in cls.ALLOWED_STATUSES:
            raise ValueError("status must be one of: " + ", ".join(sorted(cls.ALLOWED_STATUSES)))
        normalized_artifacts: Dict[str, Mapping[str, Any]] = {}
        for key, value in artifacts_raw.items():
            normalized_artifacts[str(key)] = _ensure_dict(value, f"artifacts.{key}")
        return cls(
            report_id=_ensure_str(_require_field(data, "report_id"), "report_id"),
            artifact_refs={str(k): v for k, v in artifact_refs.items()},
            status=status,
            policy_decisions=decisions,
            errors=_force_str_list(data.get("errors"), "errors"),
            artifacts=normalized_artifacts,
            execution_hash=_ensure_str(_require_field(data, "execution_hash"), "execution_hash"),
        )


__all__ = [
    "EnvSnapshotBody",
    "ExecutionReportBody",
    "PolicyDecision",
    "ProposedChangeDecision",
    "ProposedChangePlanBody",
    "LlmMetadata",
]
