"""Grammar resources for the TraceMind DSL parsers."""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Final

_GRAMMAR_PACKAGE: Final[str] = __name__


def resource_path(name: str) -> Path:
    """Return a filesystem path to the requested grammar resource."""
    with resources.as_file(resources.files(_GRAMMAR_PACKAGE) / name) as resolved:
        return resolved


__all__ = ["resource_path"]
