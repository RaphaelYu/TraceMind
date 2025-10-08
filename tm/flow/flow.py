from __future__ import annotations

from typing import Protocol

from .spec import FlowSpec


class Flow(Protocol):
    """Minimal protocol implemented by concrete flow definitions."""

    @property
    def name(self) -> str: ...

    def spec(self) -> FlowSpec: ...
