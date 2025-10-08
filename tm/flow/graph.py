from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional
import networkx as nx


class NodeKind(Enum):
    TASK = auto()
    FINISH = auto()
    SWITCH = auto()
    PARALLEL = auto()


@dataclass
class Step:
    id: str
    kind: NodeKind
    uses: Optional[str] = None
    cfg: Dict[str, Any] = field(default_factory=dict)


class FlowGraph:
    def __init__(self, name: str):
        self.name = name
        self._g = nx.DiGraph()
        self._entry: Optional[str] = None

    def task(self, node_id: str, *, uses: str, **cfg) -> str:
        self._add_node(Step(node_id, NodeKind.TASK, uses=uses, cfg=cfg))
        return node_id

    def finish(self, node_id: str) -> str:
        self._add_node(Step(node_id, NodeKind.FINISH))
        return node_id

    def switch(self, node_id: str, *, key_from: str, default: str = "_DEFAULT") -> str:
        self._add_node(Step(node_id, NodeKind.SWITCH, cfg={"key_from": key_from, "default": default}))
        return node_id

    def parallel(self, node_id: str, *, uses: List[str], max_workers: int = 4, **cfg) -> str:
        cfg = {**cfg, "uses": list(uses), "max_workers": int(max_workers)}
        self._add_node(Step(node_id, NodeKind.PARALLEL, cfg=cfg))
        return node_id

    def link(self, src: str, dst: str) -> None:
        self._g.add_edge(src, dst)

    def link_case(self, src: str, dst: str, *, case: Any) -> None:
        self._g.add_edge(src, dst, case=case)

    def set_entry(self, node_id: str) -> None:
        if node_id not in self._g:
            raise KeyError(f"Unknown node: {node_id}")
        self._entry = node_id

    def entry(self) -> str:
        if not self._entry:
            raise RuntimeError("Entry node not set")
        return self._entry

    def successors(self, node_id: str) -> List[str]:
        return list(self._g.successors(node_id))

    def node(self, node_id: str) -> Step:
        return self._g.nodes[node_id]["step"]

    def edge_attr(self, src: str, dst: str, key: str, default: Any = None) -> Any:
        return self._g.get_edge_data(src, dst, {}).get(key, default)

    def to_networkx(self) -> nx.DiGraph:
        return self._g

    def _add_node(self, step: Step) -> None:
        if step.id in self._g:
            raise ValueError(f"Duplicate node id: {step.id}")
        self._g.add_node(step.id, step=step)
        if self._entry is None:
            self._entry = step.id


def chain(flow: FlowGraph, *ids: str) -> str:
    for i in range(len(ids) - 1):
        flow.link(ids[i], ids[i + 1])
    return ids[-1]
