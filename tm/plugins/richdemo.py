from __future__ import annotations

from typing import Any, Dict

from tm.core.bus import EventBus
from tm.core.service import AppService
from tm.pipeline.engine import Plan, Rule, StepSpec


class RichDemoPlugin:
    """Sample plugin that contributes the demo pipeline plan."""

    def build_plan(self) -> Plan:
        steps = {
            "validate_services": StepSpec(
                name="validate_services",
                reads=["services[].name"],
                writes=[],
                fn=self._step_validate_services,
            ),
            "derive_status": StepSpec(
                name="derive_status",
                reads=["status", "services[].state"],
                writes=["status"],
                fn=self._step_derive_status,
            ),
        }
        rules = [
            Rule(
                name="on_services_name_change",
                triggers=["services[].name"],
                steps=["validate_services"],
            ),
            Rule(
                name="on_status_related_change",
                triggers=["status", "services[].state"],
                steps=["derive_status"],
            ),
        ]
        return Plan(steps=steps, rules=rules)

    def register_bus(self, bus: EventBus, svc: AppService) -> None:  # pragma: no cover - default no-op
        # This demo plugin does not use additional bus hooks.
        return None

    def _step_validate_services(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        new = ctx.get("new", {})
        for i, svc in enumerate(new.get("services", [])):
            name = str(svc.get("name", "")).strip()
            if not name:
                raise ValueError(f"services[{i}].name is empty")
        return ctx

    def _step_derive_status(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        new = dict(ctx.get("new", {}))
        states = [svc.get("state") for svc in new.get("services", [])]
        if states and all(s == "UP" for s in states):
            new["status"] = "ALIVE"
        elif any(s == "DOWN" for s in states):
            new["status"] = "DEGRADED"
        else:
            new["status"] = new.get("status", "REGISTERED")
        ctx["new"] = new
        ctx.setdefault("effects", []).append({"emit": "DerivedStatus", "value": new["status"]})
        return ctx


plugin = RichDemoPlugin()
