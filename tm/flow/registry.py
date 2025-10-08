from __future__ import annotations
from typing import Any, Callable, Dict, List


# Operator registry (+ metadata for static race checks)
class OperatorRegistry:
    def __init__(self):
        self._ops: Dict[str, Callable] = {}
        self._meta: Dict[str, Dict[str, Any]] = {}

    def operator(self, name: str):
        def deco(fn: Callable):
            if name in self._ops:
                raise ValueError(f"Operator already registered: {name}")
            self._ops[name] = fn
            return fn

        return deco

    def set_meta(
        self,
        name: str,
        *,
        reads: List[str] | None = None,
        writes: List[str] | None = None,
        externals: List[str] | None = None,
        pure: bool = False,
    ):
        if name not in self._ops:
            raise KeyError(f"set_meta for unknown operator: {name}")
        self._meta[name] = {
            "reads": set(reads or []),
            "writes": set(writes or []),
            "externals": set(externals or []),
            "pure": bool(pure),
        }

    def meta(self, name: str) -> Dict[str, Any]:
        return self._meta.get(name, {"reads": set(), "writes": set(), "externals": set(), "pure": False})

    def get(self, name: str) -> Callable:
        if name not in self._ops:
            raise KeyError(f"Unknown operator: {name}")
        return self._ops[name]


registry = OperatorRegistry()


# Check registry
class CheckRegistry:
    def __init__(self):
        self._checks: Dict[str, Callable] = {}

    def check(self, name: str):
        def deco(fn: Callable):
            if name in self._checks:
                raise ValueError(f"Check already registered: {name}")
            self._checks[name] = fn
            return fn

        return deco

    def get(self, name: str) -> Callable:
        if name not in self._checks:
            raise KeyError(f"Unknown check: {name}")
        return self._checks[name]


checks = CheckRegistry()
