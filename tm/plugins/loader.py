from __future__ import annotations

import importlib.metadata as md


class PluginError(RuntimeError):
    """Raised when a TraceMind plugin cannot be found or loaded."""


def load(group: str, name: str):
    eps = md.entry_points(group=group)
    entry = next((ep for ep in eps if ep.name == name), None)
    if entry is None:
        raise PluginError(f"plugin not found: {group}:{name}")
    return entry.load()()
