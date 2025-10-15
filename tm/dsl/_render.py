from __future__ import annotations

from typing import Dict, List

from .parser import RawMapping, RawMappingEntry, RawNode, RawScalar, RawSequence

"""Helpers for transforming parsed DSL nodes into serializable values."""


def render_raw_node(node: RawNode) -> object:
    if isinstance(node, RawScalar):
        return node.value
    if isinstance(node, RawSequence):
        return [render_raw_node(item) for item in node.items]
    if isinstance(node, RawMapping):
        result: Dict[str, object] = {}
        for entry in node.entries:
            if entry.key is None:
                raise ValueError("Mapping entry missing key in DSL structure")
            result[entry.key] = render_raw_node(entry.value)
        return result
    raise TypeError(f"Unsupported node type: {type(node)!r}")


def render_mapping_entries(entries: List[RawMappingEntry]) -> Dict[str, object]:
    result: Dict[str, object] = {}
    for entry in entries:
        if entry.key is None:
            raise ValueError("Mapping entry missing key in DSL structure")
        result[entry.key] = render_raw_node(entry.value)
    return result


__all__ = ["render_raw_node", "render_mapping_entries"]
