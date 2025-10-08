from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Protocol


class PolicyForbiddenError(RuntimeError):
    """Raised when a plan references a tool or flow that is not allow-listed."""

    error_code = "POLICY_FORBIDDEN"

    def __init__(self, *, kind: str, ref: str, message: Optional[str] = None) -> None:
        super().__init__(message or f"{kind} '{ref}' is not allowed")
        self.kind = kind
        self.ref = ref


class AuditSink(Protocol):
    def __call__(self, *, kind: str, ref: str, reason: str) -> None:  # pragma: no cover - protocol
        ...


@dataclass(frozen=True)
class ToolEntry:
    """Registered tool metadata."""

    tool_id: str
    handler: Callable[..., Any]
    labels: Mapping[str, str] = field(default_factory=dict)


class AllowRegistry:
    """Track allowed identifiers for tools or flows and emit audit events on violation."""

    def __init__(self, *, kind: str, audit: Optional[AuditSink] = None) -> None:
        self._kind = kind
        self._allowed: Dict[str, Mapping[str, str]] = {}
        self._audit = audit

    def allow(self, refs: Iterable[str], *, labels: Optional[Mapping[str, Mapping[str, str]]] = None) -> None:
        label_map = labels or {}
        for ref in refs:
            if not isinstance(ref, str) or not ref.strip():
                raise ValueError(f"{self._kind} id must be a non-empty string")
            normalized = ref.strip()
            meta = label_map.get(normalized, {})
            self._allowed[normalized] = dict(meta)

    def clear(self) -> None:
        self._allowed.clear()

    def is_allowed(self, ref: str) -> bool:
        return ref in self._allowed

    def require(self, ref: str, *, reason: str) -> None:
        if ref in self._allowed:
            return
        if self._audit is not None:
            self._audit(kind=self._kind, ref=ref, reason=reason)
        raise PolicyForbiddenError(kind=self._kind, ref=ref)

    def snapshot(self) -> Dict[str, Mapping[str, str]]:
        return dict(self._allowed)


class ToolRegistry:
    """Registry for runtime tools with allow-list enforcement."""

    def __init__(self, *, audit: Optional[AuditSink] = None) -> None:
        self._tools: Dict[str, ToolEntry] = {}
        self._allow = AllowRegistry(kind="tool", audit=audit)

    def register(
        self, tool_id: str, handler: Callable[..., Any], *, labels: Optional[Mapping[str, str]] = None
    ) -> ToolEntry:
        if not isinstance(tool_id, str) or not tool_id.strip():
            raise ValueError("tool_id must be a non-empty string")
        normalized = tool_id.strip()
        if normalized in self._tools:
            raise ValueError(f"Tool '{normalized}' already registered")
        entry = ToolEntry(tool_id=normalized, handler=handler, labels=dict(labels or {}))
        self._tools[normalized] = entry
        return entry

    def get(self, tool_id: str) -> ToolEntry:
        try:
            return self._tools[tool_id]
        except KeyError as exc:
            raise KeyError(f"Unknown tool '{tool_id}'") from exc

    def allow(self, refs: Iterable[str], *, labels: Optional[Mapping[str, Mapping[str, str]]] = None) -> None:
        self._allow.allow(refs, labels=labels)

    def is_allowed(self, tool_id: str) -> bool:
        return self._allow.is_allowed(tool_id)

    def require_allowed(self, tool_id: str, *, reason: str) -> None:
        self._allow.require(tool_id, reason=reason)

    def clear(self) -> None:
        self._tools.clear()
        self._allow.clear()

    def snapshot(self) -> Dict[str, ToolEntry]:
        return dict(self._tools)

    def allowed_snapshot(self) -> Dict[str, Mapping[str, str]]:
        return self._allow.snapshot()


class FlowAllowRegistry:
    """Stand-alone allow-list for flows."""

    def __init__(self, *, audit: Optional[AuditSink] = None) -> None:
        self._allow = AllowRegistry(kind="flow", audit=audit)

    def allow(self, refs: Iterable[str], *, labels: Optional[Mapping[str, Mapping[str, str]]] = None) -> None:
        self._allow.allow(refs, labels=labels)

    def is_allowed(self, flow_id: str) -> bool:
        return self._allow.is_allowed(flow_id)

    def require_allowed(self, flow_id: str, *, reason: str) -> None:
        self._allow.require(flow_id, reason=reason)

    def snapshot(self) -> Dict[str, Mapping[str, str]]:
        return self._allow.snapshot()

    def clear(self) -> None:
        self._allow.clear()


# Default singletons ---------------------------------------------------------

_audit_log: List[Dict[str, str]] = []


def _log_violation(*, kind: str, ref: str, reason: str) -> None:
    _audit_log.append({"kind": kind, "ref": ref, "reason": reason})


tool_registry = ToolRegistry(audit=_log_violation)
flow_allow_registry = FlowAllowRegistry(audit=_log_violation)


def audit_log() -> List[Dict[str, str]]:
    return list(_audit_log)


def reset_audit_log() -> None:
    _audit_log.clear()


def reset_registries() -> None:
    tool_registry.clear()
    flow_allow_registry.clear()
    reset_audit_log()


__all__ = [
    "PolicyForbiddenError",
    "ToolEntry",
    "ToolRegistry",
    "tool_registry",
    "flow_allow_registry",
    "FlowAllowRegistry",
    "AllowRegistry",
    "audit_log",
    "reset_audit_log",
    "reset_registries",
]
