from __future__ import annotations

import os
from typing import Any, Callable, Dict, Iterable, Mapping, Protocol, Tuple
from urllib.parse import ParseResult, urlparse, unquote

DEFAULT_KSTORE_URL = "jsonl://./state.jsonl"


class KStore(Protocol):
    """Minimal key-value interface used by TraceMind subsystems."""

    def put(self, key: str, value: Mapping[str, Any]) -> None:
        """Persist *value* under *key*, replacing any previous entry."""

    def get(self, key: str) -> Mapping[str, Any] | None:
        """Return the stored value for *key* or None if missing."""

    def scan(self, prefix: str) -> Iterable[Tuple[str, Mapping[str, Any]]]:
        """Yield ``(key, value)`` pairs whose keys start with *prefix*."""

    def delete(self, key: str) -> bool:
        """Remove *key* if present, returning True when removed."""

    def close(self) -> None:
        """Release any resources held by the store."""


DriverFactory = Callable[[str, ParseResult], KStore]

_DRIVERS: Dict[str, DriverFactory] = {}


def register_driver(scheme: str, factory: DriverFactory, *, overwrite: bool = False) -> None:
    key = (scheme or "").lower()
    if not key:
        raise ValueError("scheme is required for driver registration")
    if key in _DRIVERS and not overwrite:
        raise ValueError(f"driver already registered for scheme '{scheme}'")
    _DRIVERS[key] = factory


def resolve_path(parsed: ParseResult) -> str:
    """Convert a parsed URL to a filesystem path."""

    if parsed.scheme and parsed.scheme.lower() not in {"jsonl", "sqlite"}:
        # Only file-backed built-ins are supported for now.
        raise ValueError(f"unsupported KStore scheme '{parsed.scheme}'")

    raw = ""
    if parsed.netloc:
        raw = parsed.netloc
    if parsed.path:
        if raw:
            raw = raw + parsed.path
        else:
            raw = parsed.path

    raw = raw or ""
    if not raw:
        raise ValueError("kstore URL must include a path")

    if parsed.params or parsed.query or parsed.fragment:
        raise ValueError("kstore URL must not contain params/query/fragment")

    # On Windows we may receive URLs like jsonl:///C:/path; keep
    # the leading slash if it indicates an absolute drive path.
    candidate = unquote(raw)
    if os.name == "nt" and candidate.startswith("/") and len(candidate) >= 3 and candidate[2] == ":":
        candidate = candidate.lstrip("/")
    return candidate


def open_kstore(url: str | None) -> KStore:
    target = url or DEFAULT_KSTORE_URL
    parsed = urlparse(target)
    scheme = (parsed.scheme or "jsonl").lower()
    factory = _DRIVERS.get(scheme)

    if scheme == "sqlite":
        if os.getenv("NO_SQLITE") == "1":
            return _fallback_to_jsonl(target, parsed, reason="sqlite disabled via NO_SQLITE=1")
        if factory is None:
            return _fallback_to_jsonl(target, parsed, reason="sqlite driver unavailable")

    if factory is None:
        raise ValueError(f"no kstore driver registered for scheme '{scheme}'")

    try:
        return factory(target, parsed)
    except Exception:
        if scheme == "sqlite":
            return _fallback_to_jsonl(target, parsed, reason="sqlite driver failed to open")
        raise


def _fallback_to_jsonl(original_url: str, original_parsed: ParseResult, *, reason: str) -> KStore:
    del reason  # placeholder for future logging hooks
    parsed = original_parsed
    try:
        fallback_path = resolve_path(parsed)
        fallback_url = f"jsonl://{fallback_path}"
        fallback_parsed = urlparse(fallback_url)
    except Exception:
        fallback_url = DEFAULT_KSTORE_URL
        fallback_parsed = urlparse(fallback_url)

    jsonl_factory = _DRIVERS.get("jsonl")
    if jsonl_factory is None:
        raise RuntimeError("jsonl driver not registered; cannot provide fallback")
    return jsonl_factory(fallback_url, fallback_parsed)


__all__ = [
    "DEFAULT_KSTORE_URL",
    "KStore",
    "DriverFactory",
    "register_driver",
    "resolve_path",
    "open_kstore",
]

# Ensure built-in drivers register themselves even when importing the api module directly.
try:  # pragma: no cover - imports have side effects only
    from . import jsonl  # noqa: F401
except Exception:  # pragma: no cover - optional
    pass

try:  # pragma: no cover - optional dependency
    from . import sqlite  # noqa: F401
except Exception:  # pragma: no cover - optional
    pass
