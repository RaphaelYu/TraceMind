from __future__ import annotations

import json
from collections.abc import Mapping as MappingABC, Sequence as SequenceABC
from typing import Any, Mapping


def _normalize_string(value: str) -> str:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    return normalized.strip()


def _normalize_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        return _normalize_string(value)
    if isinstance(value, MappingABC):
        normalized_items = [(str(key), _normalize_value(val)) for key, val in value.items()]
        normalized_items.sort(key=lambda pair: pair[0])
        return {key: val for key, val in normalized_items}
    if isinstance(value, SequenceABC) and not isinstance(value, (str, bytes, bytearray)):
        return [_normalize_value(item) for item in value]
    return value


def normalize_body(body: Any, schema_hints: Mapping[str, Any] | None = None) -> str:
    if schema_hints is not None:  # schema hints are reserved for future use
        _ = schema_hints
    normalized = _normalize_value(body)
    return json.dumps(normalized, separators=(",", ":"), sort_keys=True, ensure_ascii=False)


__all__ = ["normalize_body"]
