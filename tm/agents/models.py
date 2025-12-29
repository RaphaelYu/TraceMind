from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Sequence


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


def _ensure_sequence(value: Any, name: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise TypeError(f"{name} must be a sequence")
    return value


def _force_list(value: Any, name: str) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise TypeError(f"{name} must be a list of strings")
    return [str(item) for item in value]


def _ensure_schema(value: Any, name: str) -> Mapping[str, Any] | str:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return dict(value)
    raise TypeError(f"{name} must be a string or mapping")


def _ensure_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{name} must be a boolean")
    return value


@dataclass
class IORef:
    ref: str
    kind: str
    schema: Mapping[str, Any] | str
    required: bool
    mode: str

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "IORef":
        return cls(
            ref=_ensure_str(_require_field(data, "ref"), "ref"),
            kind=_ensure_str(_require_field(data, "kind"), "kind"),
            schema=_ensure_schema(_require_field(data, "schema"), "schema"),
            required=_ensure_bool(_require_field(data, "required"), "required"),
            mode=_ensure_str(_require_field(data, "mode"), "mode"),
        )


@dataclass
class EffectIdempotency:
    type: str
    key_fields: List[str]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "EffectIdempotency":
        key_fields = _force_list(data.get("key_fields"), "idempotency.key_fields")
        return cls(
            type=_ensure_str(_require_field(data, "type"), "idempotency.type"),
            key_fields=key_fields,
        )


@dataclass
class EffectRef:
    name: str
    kind: str
    target: str
    idempotency: EffectIdempotency
    rollback: str | None
    evidence: Dict[str, Any]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "EffectRef":
        evidence = _ensure_dict(_require_field(data, "evidence"), "evidence")
        rollback = data.get("rollback")
        return cls(
            name=_ensure_str(_require_field(data, "name"), "name"),
            kind=_ensure_str(_require_field(data, "kind"), "kind"),
            target=_ensure_str(_require_field(data, "target"), "target"),
            idempotency=EffectIdempotency.from_mapping(
                _ensure_dict(_require_field(data, "idempotency"), "idempotency")
            ),
            rollback=_ensure_str(rollback, "rollback") if rollback is not None else None,
            evidence=evidence,
        )


@dataclass
class AgentContract:
    inputs: List[IORef]
    outputs: List[IORef]
    effects: List[EffectRef]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "AgentContract":
        inputs_raw = _ensure_sequence(_require_field(data, "inputs"), "contract.inputs")
        outputs_raw = _ensure_sequence(_require_field(data, "outputs"), "contract.outputs")
        effects_raw = _ensure_sequence(_require_field(data, "effects"), "contract.effects")
        inputs = [IORef.from_mapping(_ensure_dict(item, "contract.input")) for item in inputs_raw]
        outputs = [IORef.from_mapping(_ensure_dict(item, "contract.output")) for item in outputs_raw]
        effects = [EffectRef.from_mapping(_ensure_dict(item, "contract.effect")) for item in effects_raw]
        return cls(inputs=inputs, outputs=outputs, effects=effects)


@dataclass
class AgentRuntime:
    kind: str
    config: Dict[str, Any]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "AgentRuntime":
        config = _ensure_dict(_require_field(data, "config"), "runtime.config")
        return cls(
            kind=_ensure_str(_require_field(data, "kind"), "runtime.kind"),
            config=config,
        )


@dataclass
class AgentEvidenceOutput:
    name: str
    description: str | None = None
    target: str | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "AgentEvidenceOutput":
        return cls(
            name=_ensure_str(_require_field(data, "name"), "evidence_outputs.name"),
            description=(
                _ensure_str(data.get("description"), "evidence_outputs.description")
                if data.get("description") is not None
                else None
            ),
            target=(
                _ensure_str(data.get("target"), "evidence_outputs.target") if data.get("target") is not None else None
            ),
        )


@dataclass
class AgentSpec:
    agent_id: str
    name: str
    version: str
    runtime: AgentRuntime
    contract: AgentContract
    config_schema: Dict[str, Any]
    evidence_outputs: List[AgentEvidenceOutput]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "AgentSpec":
        runtime = AgentRuntime.from_mapping(_ensure_dict(_require_field(data, "runtime"), "runtime"))
        contract = AgentContract.from_mapping(_ensure_dict(_require_field(data, "contract"), "contract"))
        config_schema = _ensure_dict(_require_field(data, "config_schema"), "config_schema")
        evidence_outputs_raw = _ensure_sequence(_require_field(data, "evidence_outputs"), "evidence_outputs")
        evidence_outputs = [
            AgentEvidenceOutput.from_mapping(_ensure_dict(output, "evidence_outputs"))
            for output in evidence_outputs_raw
        ]
        return cls(
            agent_id=_ensure_str(_require_field(data, "agent_id"), "agent_id"),
            name=_ensure_str(_require_field(data, "name"), "name"),
            version=_ensure_str(_require_field(data, "version"), "version"),
            runtime=runtime,
            contract=contract,
            config_schema=config_schema,
            evidence_outputs=evidence_outputs,
        )


__all__ = [
    "AgentContract",
    "AgentEvidenceOutput",
    "AgentRuntime",
    "AgentSpec",
    "EffectIdempotency",
    "EffectRef",
    "IORef",
]
