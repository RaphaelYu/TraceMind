from __future__ import annotations
from typing import Dict, List, Type
from .graph import FlowGraph


class FlowBase:
    name: str = ""

    def build(self, **params) -> FlowGraph:
        raise NotImplementedError


class FlowRepo:
    def __init__(self):
        self._flows: Dict[str, Type[FlowBase]] = {}

    def register(self, flow_cls: Type[FlowBase]):
        name = getattr(flow_cls, "name", None)
        if not name:
            raise ValueError("Flow class must define `name`")
        if name in self._flows:
            raise ValueError(f"Flow already registered: {name}")
        self._flows[name] = flow_cls
        return flow_cls

    def instantiate(self, name: str, **params) -> FlowGraph:
        if name not in self._flows:
            raise KeyError(f"Unknown flow: {name}")
        return self._flows[name]().build(**params)

    def list(self) -> List[str]:
        return sorted(self._flows.keys())


flowrepo = FlowRepo()
