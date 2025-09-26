"""Binding rules that map model operations to flow names."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Iterable, Optional


class Operation(str, Enum):
    """Supported service-level operations."""

    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    ACTION = "action"


Predicate = Callable[[Dict[str, Any]], bool]


def _coerce_operation(operation: Operation | str) -> Operation:
    if isinstance(operation, Operation):
        return operation
    try:
        return Operation(operation)
    except ValueError as exc:  # pragma: no cover - defensive guard
        raise ValueError(f"Unsupported operation '{operation}'") from exc


@dataclass(frozen=True)
class BindingRule:
    """Declarative mapping between an operation and a flow."""

    operation: Operation
    flow_name: str
    predicate: Optional[Predicate] = None

    def matches(self, operation: Operation | str, ctx: Dict[str, Any]) -> bool:
        op_enum = _coerce_operation(operation)
        if self.operation is not op_enum:
            return False
        if self.predicate is None:
            return True
        return bool(self.predicate(ctx))


@dataclass
class BindingSpec:
    """Collection of binding rules for a given model."""

    model: str
    rules: Iterable[BindingRule]
    policy_endpoint: Optional[str] = None
    policy_ref: Optional[str] = None

    def __post_init__(self) -> None:
        self._rules = tuple(self.rules)

    def resolve(self, operation: Operation | str, ctx: Dict[str, Any]) -> Optional[str]:
        op_enum = _coerce_operation(operation)
        for rule in self._rules:
            if rule.matches(op_enum, ctx):
                return rule.flow_name
        return None
