from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Mapping, Sequence, Type, Union

from tm.agents.models import AgentSpec
from tm.artifacts.types import ArtifactType
from tm.controllers.models import EnvSnapshotBody, ExecutionReportBody, ProposedChangePlanBody


class ArtifactStatus(str, Enum):
    CANDIDATE = "candidate"
    ACCEPTED = "accepted"


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


def _safe_load_yaml(path: Path) -> Mapping[str, Any]:
    try:
        import yaml  # type: ignore[import-untyped]
    except ModuleNotFoundError as exc:  # pragma: no cover - rare optional dependency
        raise RuntimeError("PyYAML is required to load artifacts") from exc
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, Mapping):
        raise ValueError("artifact payload must be a mapping")
    return raw


@dataclass
class ArtifactEnvelope:
    artifact_id: str
    status: ArtifactStatus
    artifact_type: ArtifactType
    version: str
    created_by: str
    created_at: str
    body_hash: str
    envelope_hash: str
    meta: Dict[str, Any]
    signature: str | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ArtifactEnvelope":
        _meta = _ensure_dict(_require_field(data, "meta"), "meta")
        return cls(
            artifact_id=_ensure_str(_require_field(data, "artifact_id"), "artifact_id"),
            status=ArtifactStatus(_ensure_str(_require_field(data, "status"), "status")),
            artifact_type=ArtifactType(_ensure_str(_require_field(data, "artifact_type"), "artifact_type")),
            version=_ensure_str(_require_field(data, "version"), "version"),
            created_by=_ensure_str(_require_field(data, "created_by"), "created_by"),
            created_at=_ensure_str(_require_field(data, "created_at"), "created_at"),
            body_hash=_ensure_str(_require_field(data, "body_hash"), "body_hash"),
            envelope_hash=_ensure_str(_require_field(data, "envelope_hash"), "envelope_hash"),
            meta=_meta,
            signature=_ensure_str(data.get("signature"), "signature") if data.get("signature") is not None else None,
        )


def _force_list(value: Any, name: str) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise TypeError(f"{name} must be a list of strings")
    return [str(item) for item in value]


def _ensure_sequence(value: Any, name: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise TypeError(f"{name} must be a sequence")
    return value


@dataclass
class TraceLinks:
    parent_intent: str | None = None
    related_intents: List[str] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> "TraceLinks":
        if data is None:
            return cls()
        parent = data.get("parent_intent")
        related = _force_list(data.get("related_intents"), "related_intents")
        if parent is not None and not isinstance(parent, str):
            raise TypeError("trace_links.parent_intent must be a string")
        return cls(parent_intent=str(parent) if parent else None, related_intents=related)


@dataclass
class IntentBody:
    artifact_type: ClassVar[ArtifactType] = ArtifactType.INTENT
    intent_id: str
    title: str
    context: str
    goal: str
    non_goals: List[str]
    actors: List[str]
    inputs: List[str]
    outputs: List[str]
    constraints: List[str]
    success_metrics: List[str]
    risks: List[str]
    assumptions: List[str]
    trace_links: TraceLinks

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "IntentBody":
        return cls(
            intent_id=_ensure_str(_require_field(data, "intent_id"), "intent_id"),
            title=_ensure_str(_require_field(data, "title"), "title"),
            context=_ensure_str(_require_field(data, "context"), "context"),
            goal=_ensure_str(_require_field(data, "goal"), "goal"),
            non_goals=_force_list(data.get("non_goals"), "non_goals"),
            actors=_force_list(data.get("actors"), "actors"),
            inputs=_force_list(data.get("inputs"), "inputs"),
            outputs=_force_list(data.get("outputs"), "outputs"),
            constraints=_force_list(data.get("constraints"), "constraints"),
            success_metrics=_force_list(data.get("success_metrics"), "success_metrics"),
            risks=_force_list(data.get("risks"), "risks"),
            assumptions=_force_list(data.get("assumptions"), "assumptions"),
            trace_links=TraceLinks.from_mapping(data.get("trace_links")),
        )


@dataclass
class CapabilitiesBody:
    artifact_type: ClassVar[ArtifactType] = ArtifactType.CAPABILITIES
    capability_id: str
    description: str
    inputs: List[str]
    outputs: List[str]
    constraints: List[str]
    execution_binding: Dict[str, Any]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "CapabilitiesBody":
        return cls(
            capability_id=_ensure_str(_require_field(data, "capability_id"), "capability_id"),
            description=_ensure_str(_require_field(data, "description"), "description"),
            inputs=_force_list(data.get("inputs"), "inputs"),
            outputs=_force_list(data.get("outputs"), "outputs"),
            constraints=_force_list(data.get("constraints"), "constraints"),
            execution_binding=_ensure_dict(_require_field(data, "execution_binding"), "execution_binding"),
        )


@dataclass
class PlanStep:
    name: str
    reads: List[str]
    writes: List[str]
    description: str | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "PlanStep":
        return cls(
            name=_ensure_str(_require_field(data, "name"), "name"),
            reads=_force_list(data.get("reads"), "reads"),
            writes=_force_list(data.get("writes"), "writes"),
            description=(
                _ensure_str(data.get("description"), "description") if data.get("description") is not None else None
            ),
        )


@dataclass
class PlanRule:
    name: str
    triggers: List[str]
    steps: List[str]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "PlanRule":
        return cls(
            name=_ensure_str(_require_field(data, "name"), "rule.name"),
            triggers=_force_list(data.get("triggers"), "rule.triggers"),
            steps=_force_list(data.get("steps"), "rule.steps"),
        )


@dataclass
class PlanBody:
    artifact_type: ClassVar[ArtifactType] = ArtifactType.PLAN
    plan_id: str
    owner: str
    summary: str
    steps: List[PlanStep]
    rules: List[PlanRule]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "PlanBody":
        steps_raw = data.get("steps")
        if not isinstance(steps_raw, Sequence) or isinstance(steps_raw, str):
            raise TypeError("steps must be a list of step mappings")
        steps = [PlanStep.from_mapping(_ensure_dict(step, "plan step")) for step in steps_raw]
        rules_raw = data.get("rules") or []
        if rules_raw is None:
            rules_raw = []
        if not isinstance(rules_raw, Sequence) or isinstance(rules_raw, str):
            raise TypeError("rules must be a list of rule mappings")
        rules = [PlanRule.from_mapping(_ensure_dict(rule, "plan rule")) for rule in rules_raw]
        return cls(
            plan_id=_ensure_str(_require_field(data, "plan_id"), "plan_id"),
            owner=_ensure_str(_require_field(data, "owner"), "owner"),
            summary=_ensure_str(_require_field(data, "summary"), "summary"),
            steps=steps,
            rules=rules,
        )


@dataclass
class AgentBundlePlanStep:
    step: str
    agent_id: str
    phase: str | None
    inputs: List[str]
    outputs: List[str]
    description: str | None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "AgentBundlePlanStep":
        raw = _ensure_dict(data, "agent bundle plan step")
        inputs = _force_list(raw.get("inputs"), "plan.inputs")
        outputs = _force_list(raw.get("outputs"), "plan.outputs")
        return cls(
            step=_ensure_str(_require_field(raw, "step"), "plan.step"),
            agent_id=_ensure_str(_require_field(raw, "agent_id"), "plan.agent_id"),
            phase=_ensure_str(raw.get("phase"), "plan.phase") if raw.get("phase") is not None else None,
            inputs=inputs,
            outputs=outputs,
            description=(
                _ensure_str(raw.get("description"), "plan.description") if raw.get("description") is not None else None
            ),
        )


@dataclass
class AgentBundleAgent:
    spec: AgentSpec
    role: str | None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "AgentBundleAgent":
        raw = _ensure_dict(data, "agent bundle agent")
        role_value = raw.get("role")
        spec_data = dict(raw)
        spec_data.pop("role", None)
        spec = AgentSpec.from_mapping(spec_data)
        return cls(
            spec=spec,
            role=_ensure_str(role_value, "agent.role") if role_value is not None else None,
        )


@dataclass
class AgentBundleBody:
    artifact_type: ClassVar[ArtifactType] = ArtifactType.AGENT_BUNDLE
    bundle_id: str
    agents: List[AgentBundleAgent]
    plan: List[AgentBundlePlanStep]
    meta: Dict[str, Any]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "AgentBundleBody":
        agents_raw = _ensure_sequence(_require_field(data, "agents"), "agents")
        plan_raw = _ensure_sequence(_require_field(data, "plan"), "plan")
        meta_raw = data.get("meta") or {}
        return cls(
            bundle_id=_ensure_str(_require_field(data, "bundle_id"), "bundle_id"),
            agents=[AgentBundleAgent.from_mapping(_ensure_dict(agent, "agent")) for agent in agents_raw],
            plan=[AgentBundlePlanStep.from_mapping(_ensure_dict(step, "plan step")) for step in plan_raw],
            meta=_ensure_dict(meta_raw, "meta"),
        )


@dataclass
class GapMapBody:
    artifact_type: ClassVar[ArtifactType] = ArtifactType.GAP_MAP
    gap_id: str
    gap_description: str
    impacted_intents: List[str]
    mitigations: List[str]
    severity: str

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "GapMapBody":
        return cls(
            gap_id=_ensure_str(_require_field(data, "gap_id"), "gap_id"),
            gap_description=_ensure_str(_require_field(data, "gap_description"), "gap_description"),
            impacted_intents=_force_list(data.get("impacted_intents"), "impacted_intents"),
            mitigations=_force_list(data.get("mitigations"), "mitigations"),
            severity=_ensure_str(_require_field(data, "severity"), "severity"),
        )


@dataclass
class BacklogItem:
    intent_id: str
    priority: str
    description: str

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "BacklogItem":
        return cls(
            intent_id=_ensure_str(_require_field(data, "intent_id"), "intent_id"),
            priority=_ensure_str(_require_field(data, "priority"), "priority"),
            description=_ensure_str(_require_field(data, "description"), "description"),
        )


@dataclass
class BacklogBody:
    artifact_type: ClassVar[ArtifactType] = ArtifactType.BACKLOG
    backlog_id: str
    items: List[BacklogItem]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "BacklogBody":
        items_raw = data.get("items")
        if not isinstance(items_raw, Sequence) or isinstance(items_raw, str):
            raise TypeError("items must be a list of backlog entries")
        items = [BacklogItem.from_mapping(_ensure_dict(item, "backlog item")) for item in items_raw]
        return cls(
            backlog_id=_ensure_str(_require_field(data, "backlog_id"), "backlog_id"),
            items=items,
        )


ArtifactBody = Union[
    IntentBody,
    CapabilitiesBody,
    PlanBody,
    GapMapBody,
    BacklogBody,
    AgentBundleBody,
    EnvSnapshotBody,
    ProposedChangePlanBody,
    ExecutionReportBody,
]


@dataclass
class Artifact:
    envelope: ArtifactEnvelope
    body: ArtifactBody
    body_raw: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.envelope.artifact_type != self.body.artifact_type:
            raise ValueError("body artifact type does not match envelope artifact_type")


_BODY_FACTORY: Dict[ArtifactType, Type[ArtifactBody]] = {
    ArtifactType.INTENT: IntentBody,
    ArtifactType.CAPABILITIES: CapabilitiesBody,
    ArtifactType.PLAN: PlanBody,
    ArtifactType.GAP_MAP: GapMapBody,
    ArtifactType.BACKLOG: BacklogBody,
    ArtifactType.AGENT_BUNDLE: AgentBundleBody,
    ArtifactType.ENVIRONMENT_SNAPSHOT: EnvSnapshotBody,
    ArtifactType.PROPOSED_CHANGE_PLAN: ProposedChangePlanBody,
    ArtifactType.EXECUTION_REPORT: ExecutionReportBody,
}


def load_yaml_artifact(path: str | Path) -> Artifact:
    path_obj = Path(path)
    raw = _safe_load_yaml(path_obj)
    envelope_data = raw.get("envelope")
    if envelope_data is None:
        raise ValueError("artifact payload must include an 'envelope' section")
    body_data = raw.get("body")
    if body_data is None:
        raise ValueError("artifact payload must include a 'body' section")
    envelope = ArtifactEnvelope.from_mapping(_ensure_dict(envelope_data, "envelope"))
    _body_raw = _ensure_dict(body_data, "body")
    body_cls = _BODY_FACTORY[envelope.artifact_type]
    body = body_cls.from_mapping(_body_raw)
    return Artifact(envelope=envelope, body=body, body_raw=_body_raw)


__all__ = [
    "Artifact",
    "ArtifactBody",
    "ArtifactEnvelope",
    "ArtifactStatus",
    "ArtifactType",
    "BacklogBody",
    "BacklogItem",
    "CapabilitiesBody",
    "GapMapBody",
    "IntentBody",
    "PlanBody",
    "PlanRule",
    "ProposedChangePlanBody",
    "EnvSnapshotBody",
    "ExecutionReportBody",
    "TraceLinks",
    "AgentBundleAgent",
    "AgentBundleBody",
    "AgentBundlePlanStep",
    "AgentSpec",
    "load_yaml_artifact",
]
