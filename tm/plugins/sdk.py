from __future__ import annotations

from typing import Any, Mapping, Protocol

API_VERSION = "1.0"


class Exporter(Protocol):
    def setup(self, config: Mapping[str, Any]) -> None: ...

    def on_event(self, record: Mapping[str, Any]) -> None: ...

    def flush(self) -> None: ...

    def teardown(self) -> None: ...


class Tuner(Protocol):
    def select(self, flow_id: str, policy_id: str, arms: Mapping[str, Any], ctx: Mapping[str, Any]) -> str: ...

    def update(self, flow_id: str, policy_id: str, arm_id: str, reward: float) -> None: ...
