from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Iterable, Mapping, Optional, Tuple

from .operations import Operation


@dataclass(frozen=True)
class StepDef:
    """Declarative description of an individual flow step."""

    name: str
    operation: Operation
    next_steps: Tuple[str, ...] = ()
    config: Mapping[str, object] = field(default_factory=dict)
    before: Optional[Callable[[Dict[str, Any]], Optional[Awaitable[None]] | None]] = None
    run: Optional[Callable[[Dict[str, Any], Any], Any | Awaitable[Any]]] = None
    after: Optional[Callable[[Dict[str, Any], Any], Optional[Awaitable[None]] | None]] = None
    on_error: Optional[Callable[[Dict[str, Any], BaseException], Optional[Awaitable[None]] | None]] = None
    """Optional lifecycle hooks invoked by :class:`tm.flow.runtime.FlowRuntime`.

    The runtime executes hooks in the following order for each step::

        await before(ctx)
        output = await run(ctx, input)
        await after(ctx, output)

    If :func:`run` raises, :func:`after` is skipped and :func:`on_error` is awaited
    before the exception is re-raised. Missing hooks are simply ignored.
    """


@dataclass
class FlowSpec:
    """In-memory representation of a flow DAG."""

    name: str
    flow_id: Optional[str] = None
    steps: Dict[str, StepDef] = field(default_factory=dict)
    entrypoint: Optional[str] = None
    _flow_rev: int = field(init=False, default=1)

    def add_step(self, step: StepDef) -> None:
        self.steps[step.name] = step
        if self.entrypoint is None:
            self.entrypoint = step.name
        self._flow_rev += 1

    def step(self, name: str) -> StepDef:
        return self.steps[name]

    def adjacency(self) -> Dict[str, Tuple[str, ...]]:
        return {name: step.next_steps for name, step in self.steps.items()}

    def __iter__(self) -> Iterable[StepDef]:
        return iter(self.steps.values())

    def __post_init__(self) -> None:
        if self.flow_id is None:
            object.__setattr__(self, "flow_id", self.name)

    def flow_revision(self) -> str:
        """Return the current revision marker for this flow spec."""

        return f"rev-{self._flow_rev}"

    def bump_revision(self) -> None:
        """Manually increment the flow revision."""

        self._flow_rev += 1
