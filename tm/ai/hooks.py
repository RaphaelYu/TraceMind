from __future__ import annotations

from typing import Any, Dict, Optional


class DecisionHook:
    """Optional extension points around routing decisions."""

    def before_route(self, ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return None

    def after_result(self, ctx: Dict[str, Any]) -> None:
        return None


class NullDecisionHook(DecisionHook):
    """No-op hook used as the default."""

    def before_route(self, ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:  # noqa: D401
        return None

    def after_result(self, ctx: Dict[str, Any]) -> None:  # noqa: D401
        return None


__all__ = ["DecisionHook", "NullDecisionHook"]
