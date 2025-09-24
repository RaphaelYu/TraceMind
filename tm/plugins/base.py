from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from tm.core.bus import EventBus
from tm.core.service import AppService
from tm.pipeline.engine import Plan


@runtime_checkable
class Plugin(Protocol):
    """Minimal plugin contract for pipeline integrations."""

    def build_plan(self) -> Optional[Plan]:
        """Return a Plan contribution or None when no pipeline wiring is needed."""

    def register_bus(self, bus: EventBus, svc: AppService) -> None:
        """Hook into the event bus when necessary."""
