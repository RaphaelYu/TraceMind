from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Mapping, Tuple


@dataclass(frozen=True)
class PlanStats:
    nodes: int
    depth: int
    max_width: int


@dataclass(frozen=True)
class PlanResult:
    layers: Tuple[Tuple[str, ...], ...]
    stats: PlanStats


def plan(graph: Mapping[str, Iterable[str]]) -> PlanResult:
    """Compute topological layers and aggregate stats for a DAG."""
    adjacency: Dict[str, Tuple[str, ...]] = {}
    all_nodes: Dict[str, None] = {}

    for node, successors in graph.items():
        node_id = str(node)
        seen: Dict[str, None] = {}
        for succ in successors or ():
            succ_id = str(succ)
            if succ_id not in seen:
                seen[succ_id] = None
            all_nodes[succ_id] = None
        adjacency[node_id] = tuple(seen.keys())
        all_nodes[node_id] = None

    for node_id in list(all_nodes.keys()):
        adjacency.setdefault(node_id, ())

    indegree: Dict[str, int] = {node: 0 for node in adjacency}
    for targets in adjacency.values():
        for target in targets:
            indegree[target] = indegree.get(target, 0) + 1

    current_layer = sorted(node for node, degree in indegree.items() if degree == 0)
    layers: list[Tuple[str, ...]] = []
    processed = 0

    while current_layer:
        layers.append(tuple(current_layer))
        processed += len(current_layer)

        next_ready: set[str] = set()
        for node in current_layer:
            for target in adjacency[node]:
                degree = indegree[target] - 1
                indegree[target] = degree
                if degree == 0:
                    next_ready.add(target)
        current_layer = sorted(next_ready)

    total_nodes = len(adjacency)
    if processed != total_nodes:
        raise ValueError("cycle detected in flow graph")

    depth = len(layers)
    max_width = max((len(layer) for layer in layers), default=0)
    stats = PlanStats(nodes=total_nodes, depth=depth, max_width=max_width)
    return PlanResult(layers=tuple(layers), stats=stats)
