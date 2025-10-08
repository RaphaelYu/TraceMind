from __future__ import annotations
from typing import Any, Dict, List
import networkx as nx
from .graph import FlowGraph, NodeKind, Step
from .registry import OperatorRegistry


class StaticAnalyzer:
    def __init__(self, registry: OperatorRegistry):
        self.registry = registry

    def check(self, flow: FlowGraph) -> List[Dict[str, Any]]:
        g = flow.to_networkx()
        issues: List[Dict[str, Any]] = []
        if not nx.is_directed_acyclic_graph(g):
            issues.append({"kind": "cycle", "msg": "Graph contains cycles"})
        try:
            entry = flow.entry()
        except Exception:
            issues.append({"kind": "entry", "msg": "Entry node is not set"})
            entry = None
        if entry is not None:
            reachable = set(nx.descendants(g, entry)) | {entry}
            for n in g.nodes:
                if n not in reachable:
                    issues.append({"kind": "unreachable", "node": n})
        for n, data in g.nodes(data=True):
            step: Step = data.get("step")
            if step.kind == NodeKind.TASK:
                try:
                    self.registry.get(step.uses)
                except KeyError:
                    issues.append({"kind": "operator_missing", "node": n, "op": step.uses})
        return issues
