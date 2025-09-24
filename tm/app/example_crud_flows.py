from __future__ import annotations

from typing import Dict

from tm.flow.operations import Operation, ResponseMode
from tm.flow.spec import FlowSpec, StepDef


class CrudFlow:
    """Simple flow that supports create/read operations with deferred responses."""

    def __init__(self, name: str, operation: str) -> None:
        self._name = name
        self._operation = operation

    @property
    def name(self) -> str:
        return self._name

    def spec(self) -> FlowSpec:
        spec = FlowSpec(name=self._name)
        spec.add_step(
            StepDef(
                name="dispatch",
                operation=Operation.SWITCH,
                next_steps=("create", "read"),
                config={"key": self._operation},
            )
        )
        spec.add_step(
            StepDef(
                name="create",
                operation=Operation.TASK,
                next_steps=("finish",),
                config={"mode": ResponseMode.DEFERRED.value},
            )
        )
        spec.add_step(
            StepDef(
                name="read",
                operation=Operation.TASK,
                next_steps=("finish",),
                config={"mode": ResponseMode.IMMEDIATE.value},
            )
        )
        spec.add_step(
            StepDef(
                name="finish",
                operation=Operation.FINISH,
                next_steps=(),
            )
        )
        return spec


def build_flows() -> Dict[str, CrudFlow]:
    return {
        "sample.create": CrudFlow("sample.create", "create"),
        "sample.read": CrudFlow("sample.read", "read"),
    }
