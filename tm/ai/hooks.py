"""Interfaces for plugging AI-style decision hooks into routing flows."""

from __future__ import annotations

from typing import Dict, Protocol


class DecisionHook(Protocol):
    """Hook invoked around service routing decisions."""

    def before_route(self, ctx: Dict[str, object]) -> None:
        """Inspect or mutate the routing context before resolution."""

    def after_result(self, result: Dict[str, object]) -> None:
        """Observe the runtime result after execution."""


class NullDecisionHook:
    """Fallback hook that performs no action."""

    def before_route(self, ctx: Dict[str, object]) -> None:  # pragma: no cover - trivial
        return None

    def after_result(self, result: Dict[str, object]) -> None:  # pragma: no cover - trivial
        return None

