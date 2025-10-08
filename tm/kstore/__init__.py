"""Knowledge Store driver registry and helpers."""

from __future__ import annotations

from .api import DEFAULT_KSTORE_URL, KStore, open_kstore, register_driver, resolve_path

# Ensure built-in drivers are registered on import.
from . import jsonl as _jsonl_driver  # noqa: F401

try:  # pragma: no cover - optional dependency
    from . import sqlite as _sqlite_driver  # noqa: F401
except Exception:  # pragma: no cover - gracefully skip optional driver
    _sqlite_driver = None

__all__ = [
    "DEFAULT_KSTORE_URL",
    "KStore",
    "open_kstore",
    "register_driver",
    "resolve_path",
]
