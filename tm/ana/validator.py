from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Iterable, Mapping, Tuple


class IssueLevel(str, Enum):
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class ValidationIssue:
    level: IssueLevel
    code: str
    message: str
    node: str | None = None


@dataclass(frozen=True)
class ValidationReport:
    issues: Tuple[ValidationIssue, ...]

    def has_errors(self) -> bool:
        return any(issue.level == IssueLevel.ERROR for issue in self.issues)

    @property
    def errors(self) -> Tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.level == IssueLevel.ERROR)

    @property
    def warnings(self) -> Tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.level == IssueLevel.WARNING)


def validate(graph: Mapping[str, Iterable[str]]) -> ValidationReport:
    defined_nodes = {str(node) for node in graph.keys()}
    adjacency: Dict[str, Tuple[str, ...]] = {}
    all_nodes: Dict[str, None] = {}
    issues: list[ValidationIssue] = []

    def _invalid_id(node_id: str) -> bool:
        return (not node_id) or (node_id.strip() != node_id) or any(c.isspace() for c in node_id)

    duplicate_edges: Dict[str, set[str]] = {}
    unknown_targets: set[str] = set()

    for node, successors in graph.items():
        node_id = str(node)
        if _invalid_id(node_id):
            issues.append(
                ValidationIssue(
                    level=IssueLevel.ERROR,
                    code="invalid_id",
                    message="node id must be non-empty and without surrounding whitespace",
                    node=node_id,
                )
            )
        seen_targets: Dict[str, None] = {}
        duplicates_for_node: set[str] = set()
        for succ in successors or ():
            succ_id = str(succ)
            if succ_id == node_id:
                issues.append(
                    ValidationIssue(
                        level=IssueLevel.ERROR,
                        code="self_loop",
                        message="node cannot reference itself",
                        node=node_id,
                    )
                )
            if succ_id in seen_targets:
                duplicates_for_node.add(succ_id)
                continue
            seen_targets[succ_id] = None
            if succ_id not in defined_nodes:
                unknown_targets.add(succ_id)
            all_nodes[succ_id] = None
        adjacency[node_id] = tuple(seen_targets.keys())
        all_nodes[node_id] = None
        if duplicates_for_node:
            duplicate_edges[node_id] = duplicates_for_node

    for target in unknown_targets:
        issues.append(
            ValidationIssue(
                level=IssueLevel.ERROR,
                code="unknown_target",
                message=f"edge references undefined node '{target}'",
                node=target,
            )
        )

    for node_id, duplicates in duplicate_edges.items():
        for duplicate in sorted(duplicates):
            issues.append(
                ValidationIssue(
                    level=IssueLevel.WARNING,
                    code="duplicate_edge",
                    message=f"duplicate edge to '{duplicate}'",
                    node=node_id,
                )
            )

    for node_id in list(all_nodes.keys()):
        adjacency.setdefault(node_id, ())

    indegree: Dict[str, int] = {node: 0 for node in adjacency}
    for targets in adjacency.values():
        for target in targets:
            indegree[target] = indegree.get(target, 0) + 1

    roots = sorted(node for node, degree in indegree.items() if degree == 0)
    entry_root = roots[0] if roots else None

    if not roots and adjacency:
        issues.append(
            ValidationIssue(
                level=IssueLevel.ERROR,
                code="no_entrypoint",
                message="no entrypoint nodes (zero indegree) detected",
            )
        )

    if len(roots) > 1:
        for node in roots[1:]:
            issues.append(
                ValidationIssue(
                    level=IssueLevel.WARNING,
                    code="extra_entrypoint",
                    message="additional entrypoint detected",
                    node=node,
                )
            )

    # Reachability ---------------------------------------------------
    if entry_root is not None:
        visited: set[str] = set()
        stack: list[str] = [entry_root]
        while stack:
            node = stack.pop()
            if node in visited:
                continue
            visited.add(node)
            stack.extend(adjacency[node])

        unreachable = sorted(node for node in adjacency if node not in visited)
        for node_id in unreachable:
            issues.append(
                ValidationIssue(
                    level=IssueLevel.ERROR,
                    code="unreachable_node",
                    message="node is not reachable from any entrypoint",
                    node=node_id,
                )
            )

    # Cycle detection ------------------------------------------------
    indegree_work = indegree.copy()
    current_layer = sorted(node for node, degree in indegree_work.items() if degree == 0)
    processed = 0
    while current_layer:
        processed += len(current_layer)
        next_ready: set[str] = set()
        for node in current_layer:
            for target in adjacency[node]:
                indegree_work[target] -= 1
                if indegree_work[target] == 0:
                    next_ready.add(target)
        current_layer = sorted(next_ready)

    total_nodes = len(adjacency)
    if processed != total_nodes:
        cycle_nodes = sorted(node for node, degree in indegree_work.items() if degree > 0)
        issues.append(
            ValidationIssue(
                level=IssueLevel.ERROR,
                code="cycle_detected",
                message="cycle detected in flow graph",
                node=cycle_nodes[0] if cycle_nodes else None,
            )
        )

    level_rank = {IssueLevel.ERROR: 0, IssueLevel.WARNING: 1}
    issues_sorted = tuple(
        sorted(
            issues,
            key=lambda issue: (
                level_rank[issue.level],
                issue.code,
                issue.node or "",
                issue.message,
            ),
        )
    )
    return ValidationReport(issues=issues_sorted)
