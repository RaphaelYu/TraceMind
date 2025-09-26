from __future__ import annotations

import hashlib
import json
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
    _step_ids: Dict[str, str] = field(init=False, default_factory=dict)
    _rev_cache: Optional[str] = field(init=False, default=None)
    _rev_salt: int = field(init=False, default=0)

    def add_step(self, step: StepDef) -> None:
        self.steps[step.name] = step
        if self.entrypoint is None:
            self.entrypoint = step.name
        self._step_ids[step.name] = self._compute_step_id(step.name)
        self._rev_cache = None

    def step(self, name: str) -> StepDef:
        return self.steps[name]

    def adjacency(self) -> Dict[str, Tuple[str, ...]]:
        return {name: step.next_steps for name, step in self.steps.items()}

    def __iter__(self) -> Iterable[StepDef]:
        return iter(self.steps.values())

    def __post_init__(self) -> None:
        if self.flow_id is None:
            object.__setattr__(self, "flow_id", self.name)
        for name in list(self.steps):
            self._step_ids[name] = self._compute_step_id(name)
        self._rev_cache = None

    def flow_revision(self) -> str:
        """Return the current revision marker for this flow spec."""
        if self._rev_cache is None:
            payload = {
                "flow": self.name,
                "flow_id": self.flow_id,
                "entry": self.entrypoint,
                "salt": self._rev_salt,
                "steps": [
                    {
                        "name": step.name,
                        "step_id": self.step_id(step.name),
                        "operation": step.operation.name,
                        "next": list(step.next_steps),
                        "config": _canonicalize_config(step.config),
                    }
                    for step in sorted(self.steps.values(), key=lambda s: s.name)
                ],
            }
            encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            digest = hashlib.blake2s(encoded, digest_size=10).hexdigest()
            self._rev_cache = f"rev-{digest}"
        return self._rev_cache

    def bump_revision(self) -> None:
        """Manually increment the flow revision."""
        self._rev_salt += 1
        self._rev_cache = None

    def step_id(self, name: str) -> str:
        try:
            return self._step_ids[name]
        except KeyError as exc:  # pragma: no cover - defensive, lazy fill
            if name not in self.steps:
                raise KeyError(name) from exc
            step_id = self._compute_step_id(name)
            self._step_ids[name] = step_id
            return step_id

    def _compute_step_id(self, name: str) -> str:
        base = f"{self.flow_id}:{name}".encode("utf-8")
        digest = hashlib.blake2s(base, digest_size=8).hexdigest()
        return f"step-{digest}"


def _canonicalize_config(config: Mapping[str, object] | object) -> Any:
    if isinstance(config, Mapping):
        return {k: _canonicalize_config(v) for k, v in sorted(config.items())}
    if isinstance(config, (list, tuple)):
        return [_canonicalize_config(v) for v in config]
    if isinstance(config, (str, int, float, bool)) or config is None:
        return config
    return repr(config)
