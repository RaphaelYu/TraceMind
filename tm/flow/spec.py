from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, Mapping, Optional, Tuple

from .operations import Operation


@dataclass(frozen=True)
class StepDef:
    """Declarative description of an individual flow step."""

    name: str
    operation: Operation
    next_steps: Tuple[str, ...] = ()
    config: Mapping[str, object] = field(default_factory=dict)


@dataclass
class FlowSpec:
    """In-memory representation of a flow DAG."""

    name: str
    steps: Dict[str, StepDef] = field(default_factory=dict)
    entrypoint: Optional[str] = None

    def add_step(self, step: StepDef) -> None:
        self.steps[step.name] = step
        if self.entrypoint is None:
            self.entrypoint = step.name

    def step(self, name: str) -> StepDef:
        return self.steps[name]

    def adjacency(self) -> Dict[str, Tuple[str, ...]]:
        return {name: step.next_steps for name, step in self.steps.items()}

    def __iter__(self) -> Iterable[StepDef]:
        return iter(self.steps.values())
