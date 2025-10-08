from __future__ import annotations

import abc
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


class MemoryStore(abc.ABC):
    """Abstract storage for session-scoped key-value and append-only data."""

    @abc.abstractmethod
    async def get(self, session_id: str, key: str) -> Any: ...

    @abc.abstractmethod
    async def set(self, session_id: str, key: str, value: Any) -> None: ...

    @abc.abstractmethod
    async def append(self, session_id: str, key: str, item: Any) -> None: ...

    async def clear(self, session_id: str, key: Optional[str] = None) -> None:
        if key is None:
            await self._clear_session(session_id)
        else:
            await self._clear_key(session_id, key)

    async def _clear_session(self, session_id: str) -> None:
        raise NotImplementedError

    async def _clear_key(self, session_id: str, key: str) -> None:
        raise NotImplementedError


class InMemoryStore(MemoryStore):
    def __init__(self) -> None:
        self._data: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def get(self, session_id: str, key: str) -> Any:
        async with self._lock:
            return self._data.get(session_id, {}).get(key)

    async def set(self, session_id: str, key: str, value: Any) -> None:
        async with self._lock:
            self._data.setdefault(session_id, {})[key] = value

    async def append(self, session_id: str, key: str, item: Any) -> None:
        async with self._lock:
            session = self._data.setdefault(session_id, {})
            existing = session.get(key)
            if not isinstance(existing, list):
                existing = [] if existing is None else [existing]
            existing.append(item)
            session[key] = existing

    async def _clear_session(self, session_id: str) -> None:
        async with self._lock:
            self._data.pop(session_id, None)

    async def _clear_key(self, session_id: str, key: str) -> None:
        async with self._lock:
            session = self._data.get(session_id)
            if session:
                session.pop(key, None)


@dataclass
class JsonlStoreConfig:
    path: Path
    read_cache: bool = True
    flush_interval: float = 0.0  # seconds


class JsonlStore(MemoryStore):
    """Append-only JSONL backed store with optional in-memory cache."""

    def __init__(self, config: JsonlStoreConfig) -> None:
        self._config = config
        self._path = config.path
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if self._path.exists() and config.read_cache:
            self._load()

    def _load(self) -> None:
        try:
            with self._path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    record = json.loads(line)
                    session = record.get("session_id")
                    key = record.get("key")
                    value = record.get("value")
                    if isinstance(session, str) and isinstance(key, str):
                        self._cache.setdefault(session, {})[key] = value
        except FileNotFoundError:
            return

    async def get(self, session_id: str, key: str) -> Any:
        async with self._lock:
            if session_id in self._cache and key in self._cache[session_id]:
                return self._cache[session_id][key]
        return None

    async def set(self, session_id: str, key: str, value: Any) -> None:
        record = {"session_id": session_id, "key": key, "value": value}
        async with self._lock:
            self._cache.setdefault(session_id, {})[key] = value
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    async def append(self, session_id: str, key: str, item: Any) -> None:
        async with self._lock:
            current = self._cache.setdefault(session_id, {}).get(key)
            if not isinstance(current, list):
                current = [] if current is None else [current]
            current.append(item)
            self._cache[session_id][key] = current
            record = {"session_id": session_id, "key": key, "value": current}
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    async def _clear_session(self, session_id: str) -> None:
        async with self._lock:
            self._cache.pop(session_id, None)
            self._rewrite()

    async def _clear_key(self, session_id: str, key: str) -> None:
        async with self._lock:
            session = self._cache.get(session_id)
            if session and key in session:
                session.pop(key)
                self._rewrite()

    def _rewrite(self) -> None:
        with self._path.open("w", encoding="utf-8") as handle:
            for session_id, kv in self._cache.items():
                for key, value in kv.items():
                    record = {"session_id": session_id, "key": key, "value": value}
                    handle.write(json.dumps(record, ensure_ascii=False) + "\n")


__all__ = [
    "MemoryStore",
    "InMemoryStore",
    "JsonlStore",
    "JsonlStoreConfig",
]
