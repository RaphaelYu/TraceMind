from __future__ import annotations
import importlib, os
from typing import List, Optional
from .base import Plugin

def _split_csv(env: str) -> List[str]:
    return [x.strip() for x in (env or "").split(",") if x.strip()]

def load_plugins() -> List[Plugin]:
    """
    Discovery order:
    1) env TRACE_PLUGINS="pkgA:mod:obj,pkgB.plugin:Plugin"
       - item can be "package.module:object" or "package.module"
         (then it must expose 'plugin' variable)
    2) local dev folder via TRACE_PLUGINS_PATH="plugins_local"
       - imports as 'plugins_local.richdemo:plugin' etc.
    """
    plugs: List[Plugin] = []
    # explicit list
    for spec in _split_csv(os.getenv("TRACE_PLUGINS", "")):
        mod_name, _, obj_name = spec.partition(":")
        mod = importlib.import_module(mod_name)
        obj = getattr(mod, obj_name or "plugin")
        plugs.append(obj)  # obj must satisfy Plugin protocol

    # optional path-based discovery (dev convenience)
    extra_path = os.getenv("TRACE_PLUGINS_PATH")
    if extra_path and extra_path not in map(str, __import__("sys").path):
        __import__("sys").path.append(extra_path)

    return plugs
