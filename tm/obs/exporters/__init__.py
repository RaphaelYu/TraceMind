"""Exporter registry for metric output plugins."""

from __future__ import annotations

from typing import Callable, Dict, Mapping, Optional, Protocol

from tm.obs.counters import Registry
from tm.obs import counters

metrics = counters.metrics


class Exporter(Protocol):
    """Interface implemented by metric exporters."""

    def start(self, registry: Registry) -> None:
        """Begin exporting using the provided registry."""

    def stop(self) -> None:
        """Stop exporting and release resources."""

    def export(self, snapshot: Mapping[str, object]) -> None:
        """Export a single snapshot immediately."""


ExporterFactory = Callable[[Registry], Optional[Exporter]]

_FACTORIES: Dict[str, ExporterFactory] = {}


def register_exporter(name: str, factory: ExporterFactory) -> None:
    """Register a named exporter factory for later instantiation."""

    _FACTORIES[name] = factory


def get_exporter_factory(name: str) -> Optional[ExporterFactory]:
    return _FACTORIES.get(name)


def list_exporters() -> Dict[str, ExporterFactory]:
    return dict(_FACTORIES)


__all__ = [
    "Exporter",
    "ExporterFactory",
    "register_exporter",
    "get_exporter_factory",
    "list_exporters",
    "metrics",
]
