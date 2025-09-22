from __future__ import annotations
from typing import Protocol, Optional, List, Callable, Any
from tm.pipeline.engine import Plan
from tm.core.bus import EventBus
from tm.core.service import AppService

class Plugin(Protocol):
    """Minimal plugin interface. All methods are optional."""
    name: str
    version: str

    def build_plan(self) -> Optional[Plan]: ...
    def register_bus(self, bus: EventBus, app: AppService) -> None: ...
    def register_dag(self) -> None: ...
    def register_skills(self) -> None: ...
