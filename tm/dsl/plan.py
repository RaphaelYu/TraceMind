from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .ir import (
    SourceSpan,
    WdlCallStep,
    WdlStep,
    WdlWhenStep,
    WdlWorkflow,
    build_wdl_ir,
)
from .parser import DslParseError, parse_wdl


class PlanError(RuntimeError):
    """Raised when a workflow plan cannot be generated."""


@dataclass(frozen=True)
class PlanNode:
    id: str
    type: str
    label: str
    target: Optional[str]
    location: SourceSpan


@dataclass(frozen=True)
class PlanEdge:
    source: str
    target: str
    label: Optional[str] = None


@dataclass(frozen=True)
class WorkflowPlan:
    name: str
    version: str
    entry: Optional[str]
    nodes: Tuple[PlanNode, ...]
    edges: Tuple[PlanEdge, ...]
    source: Optional[Path] = None


def plan_text(text: str, *, filename: Optional[str] = None) -> WorkflowPlan:
    try:
        document = parse_wdl(text, filename=filename)
        workflow = build_wdl_ir(document)
    except DslParseError as exc:
        raise PlanError(str(exc)) from exc
    return build_workflow_plan(workflow, source=Path(filename) if filename else None)


def plan_path(path: Path) -> WorkflowPlan:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PlanError(f"Unable to read '{path}': {exc}") from exc
    return plan_text(text, filename=str(path))


def plan_paths(paths: Sequence[Path]) -> List[Tuple[Path, WorkflowPlan]]:
    plans: List[Tuple[Path, WorkflowPlan]] = []
    for path in _discover_wdl_files(paths):
        plans.append((path, plan_path(path)))
    if not plans:
        raise PlanError("No WDL files found to plan")
    return plans


def build_workflow_plan(workflow: WdlWorkflow, *, source: Optional[Path] = None) -> WorkflowPlan:
    planner = _WorkflowPlanner(workflow)
    entry, nodes, edges = planner.build()
    return WorkflowPlan(
        name=workflow.name,
        version=workflow.version,
        entry=entry,
        nodes=tuple(nodes),
        edges=tuple(edges),
        source=source,
    )


def plan_to_dict(plan: WorkflowPlan) -> Dict[str, object]:
    return {
        "workflow": plan.name,
        "version": plan.version,
        "entry": plan.entry,
        "source": str(plan.source) if plan.source else None,
        "nodes": [
            {
                "id": node.id,
                "type": node.type,
                "label": node.label,
                "target": node.target,
                "location": {
                    "line": node.location.line,
                    "column": node.location.column,
                    "filename": str(node.location.filename) if node.location.filename else None,
                },
            }
            for node in plan.nodes
        ],
        "edges": [
            {
                "from": edge.source,
                "to": edge.target,
                "label": edge.label,
            }
            for edge in plan.edges
        ],
    }


def plan_to_dot(plan: WorkflowPlan) -> str:
    lines = [f'digraph "{plan.name}" {{']
    for node in plan.nodes:
        label = f"{node.label}"
        if node.type == "condition":
            label = f"{node.label}\\n[condition]"
        elif node.target:
            label = f"{node.label}\\n{node.target}"
        lines.append(f'  "{node.id}" [label="{label}"];')
    for edge in plan.edges:
        if edge.label:
            lines.append(f'  "{edge.source}" -> "{edge.target}" [label="{edge.label}"];')
        else:
            lines.append(f'  "{edge.source}" -> "{edge.target}";')
    lines.append("}")
    return "\n".join(lines)


def _discover_wdl_files(paths: Sequence[Path]) -> List[Path]:
    seen: Dict[Path, None] = {}
    for candidate in paths:
        if candidate.is_file():
            if candidate.suffix.lower() == ".wdl":
                seen.setdefault(candidate.resolve(), None)
        elif candidate.is_dir():
            for nested in candidate.rglob("*.wdl"):
                if nested.is_file():
                    seen.setdefault(nested.resolve(), None)
    return sorted(seen.keys())


class _WorkflowPlanner:
    def __init__(self, workflow: WdlWorkflow) -> None:
        self.workflow = workflow
        self.nodes: Dict[str, PlanNode] = {}
        self.edges: List[PlanEdge] = []
        self.when_counter = 0
        self.entry: Optional[str] = None
        self.true_pending: Dict[str, str] = {}
        self.false_pending: Dict[str, str] = {}

    def build(self) -> Tuple[Optional[str], Tuple[PlanNode, ...], Tuple[PlanEdge, ...]]:
        self._process_sequence(self.workflow.steps, prev_exits=[])
        nodes = tuple(self.nodes.values())
        edges = tuple(self.edges)
        return self.entry, nodes, edges

    # ------------------------------------------------------------------ sequence processing
    def _process_sequence(self, steps: Sequence[WdlStep], prev_exits: Iterable[str]) -> List[str]:
        exits = list(prev_exits)
        for step in steps:
            if isinstance(step, WdlCallStep):
                exits = self._process_call(step, exits)
            elif isinstance(step, WdlWhenStep):
                exits = self._process_when(step, exits)
        return exits

    def _process_call(self, step: WdlCallStep, prev_exits: Iterable[str]) -> List[str]:
        node_id = step.step_id
        if node_id not in self.nodes:
            self.nodes[node_id] = PlanNode(
                id=node_id,
                type="call",
                label=step.step_id,
                target=step.target,
                location=step.location,
            )
        self._connect(prev_exits, node_id)
        if self.entry is None:
            self.entry = node_id
        return [node_id]

    def _process_when(self, step: WdlWhenStep, prev_exits: Iterable[str]) -> List[str]:
        cond_id = self._next_condition_id()
        label = step.condition.strip()
        self.nodes.setdefault(
            cond_id,
            PlanNode(
                id=cond_id,
                type="condition",
                label=label,
                target=None,
                location=step.location,
            ),
        )
        self._connect(prev_exits, cond_id)
        if self.entry is None and not list(prev_exits):
            self.entry = cond_id

        true_label = f"if {label}"
        false_label = f"else not({label})"
        self.true_pending[cond_id] = true_label
        self.false_pending[cond_id] = false_label

        branch_exits = self._process_sequence(step.steps, prev_exits=[cond_id])
        # True branch consumes the pending label; ensure residual mapping cleaned
        self.true_pending.pop(cond_id, None)
        # Return both branch exits and condition node for fall-through
        return [cond_id] + branch_exits

    # ------------------------------------------------------------------ helpers
    def _connect(self, sources: Iterable[str], target: str) -> None:
        sources = list(sources)
        if not sources:
            if self.entry is None:
                self.entry = target
            return
        for src in sources:
            label = None
            if src in self.true_pending:
                label = self.true_pending.pop(src)
            elif src in self.false_pending:
                label = self.false_pending[src]
                # remove after first connection
                self.false_pending.pop(src, None)
            self.edges.append(PlanEdge(source=src, target=target, label=label))

    def _next_condition_id(self) -> str:
        ident = f"when_{self.when_counter}"
        self.when_counter += 1
        return ident


__all__ = [
    "PlanError",
    "PlanNode",
    "PlanEdge",
    "WorkflowPlan",
    "plan_path",
    "plan_paths",
    "plan_text",
    "build_workflow_plan",
    "plan_to_dict",
    "plan_to_dot",
]
