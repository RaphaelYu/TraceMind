from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence


@dataclass(frozen=True)
class MissingCapabilityError(RuntimeError):
    capability_id: str
    step_id: str | None

    def __post_init__(self) -> None:
        message = f"capability '{self.capability_id}' missing for step '{self.step_id or 'unknown'}'"
        super().__init__(message)


@dataclass(frozen=True)
class StepPlan:
    step_id: str
    capability_id: str
    guard: Mapping[str, Any] | None
    events: tuple[str, ...]
    produces: Mapping[str, Any]


def plan_workflow_steps(workflow: Mapping[str, Any], capabilities: Sequence[Mapping[str, Any]]) -> tuple[StepPlan, ...]:
    spec_lookup = _build_capability_lookup(capabilities)
    steps = workflow.get("steps") or []
    result: list[StepPlan] = []
    for step in steps:
        step_id = str(step.get("step_id") or "")
        capability_id = str(step.get("capability_id") or "")
        spec = spec_lookup.get(capability_id)
        if spec is None:
            raise MissingCapabilityError(capability_id=capability_id, step_id=step_id)
        events = tuple(_extract_event_names(spec))
        produces = _extract_state_produces(spec)
        guard = step.get("guard")
        result.append(
            StepPlan(step_id=step_id, capability_id=capability_id, guard=guard, events=events, produces=produces)
        )
    return tuple(result)


def build_state_trace(
    workflow: Mapping[str, Any], capabilities: Sequence[Mapping[str, Any]]
) -> tuple[list[Mapping[str, Any]], Mapping[str, Any]]:
    plans = plan_workflow_steps(workflow, capabilities)
    state: dict[str, Any] = {}
    trace: list[Mapping[str, Any]] = []
    for plan in plans:
        state.update(plan.produces)
        trace.append(
            {
                "step_id": plan.step_id,
                "capability_id": plan.capability_id,
                "events": list(plan.events),
                "state_snapshot": dict(state),
                "guard": plan.guard,
            }
        )
    return trace, dict(state)


def _build_capability_lookup(capabilities: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    lookup: dict[str, Mapping[str, Any]] = {}
    for spec in capabilities:
        if not isinstance(spec, Mapping):
            continue
        capability_id = spec.get("capability_id")
        if capability_id is None:
            continue
        lookup[str(capability_id)] = spec
    return lookup


def _extract_event_names(spec: Mapping[str, Any]) -> Iterable[str]:
    for event in spec.get("event_types") or []:
        if isinstance(event, Mapping):
            name = event.get("name")
            if isinstance(name, str) and name:
                yield name


def _extract_state_produces(spec: Mapping[str, Any]) -> dict[str, Any]:
    produces: dict[str, Any] = {}
    for extractor in spec.get("state_extractors") or []:
        if not isinstance(extractor, Mapping):
            continue
        payload = extractor.get("produces") or {}
        if not isinstance(payload, Mapping):
            continue
        for key, value in payload.items():
            produces[key] = _resolve_value(value)
    return produces


def _resolve_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        if "value" in value:
            return value["value"]
        return {key: _resolve_value(val) for key, val in value.items()}
    return value
