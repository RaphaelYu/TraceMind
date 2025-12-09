from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import ast
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, cast

from ._render import render_raw_node
from .ir import (
    SourceSpan,
    WdlCallStep,
    WdlOutput,
    WdlStep,
    WdlWhenStep,
    WdlWorkflow,
)


class FlowCompileError(ValueError):
    """Raised when a WDL workflow cannot be compiled into a Flow specification."""


@dataclass(frozen=True)
class ExitEdge:
    src: str
    case: Optional[str] = None


@dataclass(frozen=True)
class SequenceGraph:
    entry: str
    exits: Tuple[ExitEdge, ...]


@dataclass(frozen=True)
class FlowCompilation:
    flow_id: str
    data: Dict[str, object]
    source: Optional[Path]
    step_sources: Dict[str, SourceSpan]
    workflow: WdlWorkflow


class _FlowBuilder:
    DEFAULT_CASE = "_DEFAULT"

    def __init__(self, workflow: WdlWorkflow, *, source: Optional[Path]) -> None:
        self.workflow = workflow
        self.source = source
        self._steps: Dict[str, Dict[str, object]] = {}
        self._edges: List[Dict[str, object]] = []
        self._step_sources: Dict[str, SourceSpan] = {}
        self._entry: Optional[str] = None
        self._switch_counter = 0

    def compile(self) -> FlowCompilation:
        if not self.workflow.steps:
            raise FlowCompileError("Workflow must contain at least one step")

        main = self._compile_sequence(self.workflow.steps)
        outputs_segment = self._add_outputs_step(list(self.workflow.outputs))
        self._link_segments(main.exits, outputs_segment.entry)
        finish_segment = self._add_finish_step()
        self._link_segments(outputs_segment.exits, finish_segment.entry)

        flow_steps = list(self._steps.values())
        flow: Dict[str, object] = {
            "flow": {
                "id": self.workflow.name,
                "version": self.workflow.version,
                "entry": self._entry or outputs_segment.entry,
                "steps": flow_steps,
                "edges": self._edges,
                "metadata": {
                    "dsl": {
                        "version": self.workflow.version,
                        "source": str(self.source) if self.source else None,
                        "steps": {
                            step_id: {
                                "line": span.line,
                                "column": span.column,
                                "filename": str(span.filename) if span.filename else None,
                            }
                            for step_id, span in self._step_sources.items()
                        },
                    }
                },
            }
        }
        return FlowCompilation(
            flow_id=self.workflow.name,
            data=flow,
            source=self.source,
            step_sources=dict(self._step_sources),
            workflow=self.workflow,
        )

    def _compile_sequence(self, steps: Sequence[WdlStep]) -> SequenceGraph:
        entry: Optional[str] = None
        exits: List[ExitEdge] = []

        for step in steps:
            segment = self._compile_step(step)
            if entry is None:
                entry = segment.entry
            if not exits:
                exits = list(segment.exits)
            else:
                self._link_segments(tuple(exits), segment.entry)
                exits = list(segment.exits)
        if entry is None:
            raise FlowCompileError("Empty step sequence encountered during compilation")
        return SequenceGraph(entry=entry, exits=tuple(exits))

    def _compile_step(self, step: WdlStep) -> SequenceGraph:
        if isinstance(step, WdlCallStep):
            return self._compile_call(step)
        if isinstance(step, WdlWhenStep):
            return self._compile_when(step)
        raise TypeError(f"Unsupported step type: {type(step)!r}")

    def _compile_call(self, step: WdlCallStep) -> SequenceGraph:
        if step.step_id in self._steps:
            raise FlowCompileError(f"Duplicate step id '{step.step_id}' in workflow")
        config = {
            "call": {
                "target": step.target,
                "args": {arg.name: render_raw_node(arg.value) for arg in step.args},
            }
        }
        self._add_step(
            {
                "id": step.step_id,
                "kind": "task",
                "config": config,
                "hooks": {"run": "tm.dsl.runtime.call"},
            },
            step.location,
        )
        return SequenceGraph(entry=step.step_id, exits=(ExitEdge(step.step_id),))

    def _compile_when(self, step: WdlWhenStep) -> SequenceGraph:
        condition = _parse_condition(step.condition, step.location)
        switch_id = self._unique_step_id(prefix="when")
        config = {
            "key_from": condition.key_from,
            "cases": {},
            "default": self.DEFAULT_CASE,
        }

        self._add_step(
            {
                "id": switch_id,
                "kind": "switch",
                "config": config,
                "hooks": {"run": "tm.dsl.runtime.switch"},
            },
            step.location,
        )

        nested = self._compile_sequence(step.steps)
        # Update switch config with case targets
        switch_step = self._steps[switch_id]
        switch_config = switch_step.get("config")
        if not isinstance(switch_config, dict):
            raise FlowCompileError("Switch step missing configuration during compilation")
        cases = cast(Dict[str, str], switch_config.setdefault("cases", {}))
        for case_value in condition.case_values:
            cases[case_value] = nested.entry
            self._add_edge(switch_id, nested.entry, case=case_value)

        exits = list(nested.exits)
        exits.append(ExitEdge(switch_id, self.DEFAULT_CASE))
        return SequenceGraph(entry=switch_id, exits=tuple(exits))

    def _add_outputs_step(self, outputs: Sequence[WdlOutput]) -> SequenceGraph:
        step_id = self._unique_step_id(prefix="emit")
        config = {
            "outputs": {item.name: render_raw_node(item.value) for item in outputs},
        }
        location = outputs[0].location if outputs else self.workflow.location
        self._add_step(
            {
                "id": step_id,
                "kind": "task",
                "config": config,
                "hooks": {"run": "tm.dsl.runtime.emit_outputs"},
            },
            location,
        )
        return SequenceGraph(entry=step_id, exits=(ExitEdge(step_id),))

    def _add_finish_step(self) -> SequenceGraph:
        step_id = self._unique_step_id(prefix="finish")
        self._add_step({"id": step_id, "kind": "finish"}, self.workflow.location)
        return SequenceGraph(entry=step_id, exits=())

    def _add_step(self, step: Dict[str, object], location: SourceSpan) -> None:
        step_id = step.get("id")
        if not isinstance(step_id, str):
            raise FlowCompileError("Step identifier must be a string")
        if step_id in self._steps:
            raise FlowCompileError(f"Duplicate step id '{step_id}' generated during compilation")
        self._steps[step_id] = step
        self._step_sources[step_id] = location
        if self._entry is None:
            self._entry = step_id

    def _add_edge(self, src: str, dst: str, *, case: Optional[str] = None) -> None:
        record: Dict[str, object] = {"from": src, "to": dst}
        if case is not None:
            record["when"] = case
            step = self._steps.get(src)
            if step is not None and step.get("kind") == "switch":
                config = step.get("config")
                if isinstance(config, dict):
                    cases = config.setdefault("cases", {})
                    if isinstance(cases, dict) and case not in cases:
                        cases[case] = dst
        self._edges.append(record)

    def _link_segments(self, exits: Iterable[ExitEdge], entry: str) -> None:
        for exit_edge in exits:
            self._add_edge(exit_edge.src, entry, case=exit_edge.case)

    def _unique_step_id(self, *, prefix: str) -> str:
        while True:
            candidate = f"{prefix}_{self._switch_counter}"
            self._switch_counter += 1
            if candidate not in self._steps:
                return candidate


@dataclass(frozen=True)
class _Condition:
    key_from: str
    case_values: Tuple[str, ...]


def _parse_condition(text: str, location: SourceSpan) -> _Condition:
    stripped = text.strip()
    if " in " in stripped:
        ref, _, remainder = stripped.partition(" in ")
        values = _parse_literal_list(remainder.strip(), location)
        key_from = _reference_to_path(ref.strip(), location)
        return _Condition(key_from=key_from, case_values=tuple(values))
    if "==" in stripped:
        ref, _, value = stripped.partition("==")
        key_from = _reference_to_path(ref.strip(), location)
        literal = _parse_literal(value.strip(), location)
        return _Condition(key_from=key_from, case_values=(literal,))
    raise FlowCompileError(f"Unsupported when condition '{text}' at line {location.line}")


def _parse_literal_list(text: str, location: SourceSpan) -> List[str]:
    try:
        parsed = ast.literal_eval(text)
    except Exception as exc:
        raise FlowCompileError(f"Invalid literal list in condition at line {location.line}: {exc}") from exc
    if not isinstance(parsed, (list, tuple)):
        raise FlowCompileError(f"Expected list literal in condition at line {location.line}")
    values: List[str] = []
    for item in parsed:
        if not isinstance(item, str):
            raise FlowCompileError("Conditional branch values must be strings")
        values.append(item)
    if not values:
        raise FlowCompileError("Condition list must contain at least one value")
    return values


def _parse_literal(text: str, location: SourceSpan) -> str:
    try:
        parsed = ast.literal_eval(text)
    except Exception as exc:
        raise FlowCompileError(f"Invalid literal in condition at line {location.line}: {exc}") from exc
    if not isinstance(parsed, str):
        raise FlowCompileError("Conditional value must be a string literal")
    return parsed


def _reference_to_path(ref: str, location: SourceSpan) -> str:
    if ref.startswith("$input."):
        suffix = ref[len("$input.") :]
        return f"$.inputs.{suffix}"
    if ref.startswith("$step."):
        suffix = ref[len("$step.") :]
        return f"$.vars.{suffix}"
    raise FlowCompileError(f"Unsupported reference '{ref}' in condition at line {location.line}")


def compile_workflow(workflow: WdlWorkflow, *, source: Optional[Path] = None) -> FlowCompilation:
    """Compile a WdlWorkflow into a Flow specification."""
    builder = _FlowBuilder(workflow, source=source)
    return builder.compile()


__all__ = ["FlowCompilation", "FlowCompileError", "compile_workflow"]
