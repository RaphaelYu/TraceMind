from __future__ import annotations

import importlib
import importlib.metadata as md
from types import ModuleType
from typing import Any, Iterable, List, Sequence, cast

from tm.plugins.base import Plugin

DEFAULT_GROUPS: tuple[str, ...] = ("tm.plugins", "tm.plugins_local")
DEFAULT_MODULES: tuple[str, ...] = ("tm.plugins.richdemo", "tm.plugins_local.richdemon")


class PluginError(RuntimeError):
    """Raised when a TraceMind plugin cannot be found or loaded."""


def _load_entry_points(groups: Iterable[str]) -> List[Plugin]:
    plugins: list[Plugin] = []
    for group in groups:
        try:
            eps: Sequence[Any] = ()
            raw = md.entry_points()
            if hasattr(raw, "select"):  # py311+
                eps = list(raw.select(group=group))
            elif isinstance(raw, dict):  # py310 legacy typing
                eps = list(raw.get(group, []))
            else:
                eps = list(md.entry_points(group=group))
        except Exception:
            eps = ()
        for ep in eps:
            try:
                plugin_obj = ep.load()()
                plugins.append(cast(Plugin, plugin_obj))
            except Exception as exc:  # pragma: no cover - defensive
                name = getattr(ep, "name", "<unknown>")
                raise PluginError(f"failed to load plugin {group}:{name}: {exc}") from exc
    return plugins


def _load_modules(mod_names: Iterable[str]) -> List[Plugin]:
    plugins: list[Plugin] = []
    for mod_name in mod_names:
        try:
            mod: ModuleType = importlib.import_module(mod_name)
        except ImportError:
            continue
        plugin_obj = getattr(mod, "plugin", None)
        if plugin_obj is not None:
            plugins.append(cast(Plugin, plugin_obj))
    return plugins


def load_plugins(groups: Iterable[str] = DEFAULT_GROUPS, modules: Iterable[str] = DEFAULT_MODULES) -> List[Plugin]:
    """Load available plugins.

    Priority:
    1) entry_points under provided groups (default: tm.plugins / tm.plugins_local)
    2) fallback modules that expose a top-level `plugin` object
    """
    plugins = _load_entry_points(groups)
    if plugins:
        return plugins
    return _load_modules(modules)


def load(group: str, name: str):
    eps = md.entry_points(group=group)
    entry = next((ep for ep in eps if ep.name == name), None)
    if entry is None:
        raise PluginError(f"plugin not found: {group}:{name}")
    return entry.load()()
