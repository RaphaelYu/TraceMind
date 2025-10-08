from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from .spec import FlowSpec


@dataclass
class ValidationIssue:
    kind: str
    message: str
    step: Optional[str] = None


class FlowInspector:
    """Static checker + artifact exporter for FlowSpec objects."""

    def __init__(self, spec: FlowSpec) -> None:
        self.spec = spec

    def validate(self) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        issues.extend(self._check_cycle())
        issues.extend(self._check_reachability())
        issues.extend(self._check_switch_targets())
        return issues

    def export_json(self) -> Dict[str, object]:
        return {
            "flow": self.spec.name,
            "flow_id": self.spec.flow_id,
            "flow_rev": self.spec.flow_revision(),
            "entry": self.spec.entrypoint,
            "steps": [
                {
                    "name": step.name,
                    "step_id": self.spec.step_id(step.name),
                    "operation": step.operation.name,
                    "next": list(step.next_steps),
                    "config": dict(step.config),
                }
                for step in self.spec
            ],
        }

    def export_mermaid(self) -> str:
        lines = ["flowchart TD"]
        for step in self.spec:
            label = f"{step.name}{step.operation.name.lower()}"
            lines.append(f"    {step.name}[{label}]")
            for nxt in step.next_steps:
                lines.append(f"    {step.name} --> {nxt}")
        return "\n".join(lines)

    def export_plantuml(self) -> str:
        lines = ["@startuml"]
        for step in self.spec:
            lines.append(f"state {step.name}")
        for step in self.spec:
            for nxt in step.next_steps:
                lines.append(f"{step.name} --> {nxt}")
        lines.append("@enduml")
        return "\n".join(lines)

    def _check_cycle(self) -> List[ValidationIssue]:
        visited: Dict[str, bool] = {}
        stack: Dict[str, bool] = {}
        issues: List[ValidationIssue] = []

        def dfs(node: str) -> None:
            visited[node] = True
            stack[node] = True
            for nxt in self.spec.step(node).next_steps:
                if nxt not in self.spec.steps:
                    issues.append(ValidationIssue("dangling", f"Unknown target '{nxt}'", node))
                    continue
                if not visited.get(nxt, False):
                    dfs(nxt)
                elif stack.get(nxt, False):
                    issues.append(ValidationIssue("cycle", f"Cycle detected via {node}->{nxt}", nxt))
            stack.pop(node, None)

        entry = self.spec.entrypoint
        if entry is None:
            issues.append(ValidationIssue("entry", "Entrypoint not defined"))
            return issues

        for step_name in self.spec.steps:
            visited.setdefault(step_name, False)

        dfs(entry)
        return issues

    def _check_reachability(self) -> List[ValidationIssue]:
        if not self.spec.entrypoint:
            return []
        reachable = set()

        def walk(name: str) -> None:
            if name in reachable:
                return
            reachable.add(name)
            for nxt in self.spec.step(name).next_steps:
                if nxt in self.spec.steps:
                    walk(nxt)

        walk(self.spec.entrypoint)
        unreachable = [name for name in self.spec.steps if name not in reachable]
        return [ValidationIssue("unreachable", f"Step '{name}' unreachable", name) for name in unreachable]

    def _check_switch_targets(self) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        for step in self.spec:
            if step.operation is not None and step.operation.name == "SWITCH":
                for nxt in step.next_steps:
                    if nxt not in self.spec.steps:
                        issues.append(ValidationIssue("dangling", f"Switch target '{nxt}' missing", step.name))
        return issues
