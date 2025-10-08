from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from tm.pipeline.engine import Plan
from tm.app.rich_demo_plan import build_plan  # reuse your plan file


@dataclass
class _RichDemoPlugin:
    name: str = "rich-demo"
    version: str = "0.1.0"

    def build_plan(self) -> Optional[Plan]:
        return build_plan()

    def register_bus(self, bus, app) -> None:
        # Optional: subscribe to events for logging/metrics
        def _on(ev):
            if ev.__class__.__name__ == "ObjectUpserted":
                # add minimal observability if needed
                pass

        bus.subscribe(_on)


plugin = _RichDemoPlugin()
