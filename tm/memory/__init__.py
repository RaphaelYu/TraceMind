from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .store import InMemoryStore, JsonlStore, JsonlStoreConfig, MemoryStore


@dataclass
class MemoryConfig:
    backend: str = "memory"  # memory | jsonl
    path: Optional[str] = None


_memory_store: MemoryStore = InMemoryStore()


def configure_memory(config: MemoryConfig) -> None:
    global _memory_store
    if config.backend == "memory":
        _memory_store = InMemoryStore()
    elif config.backend == "jsonl":
        if not config.path:
            raise ValueError("jsonl backend requires 'path'")
        _memory_store = JsonlStore(JsonlStoreConfig(path=Path(config.path)))
    else:
        raise ValueError(f"Unsupported memory backend: {config.backend}")


def current_store() -> MemoryStore:
    return _memory_store


__all__ = [
    "MemoryStore",
    "InMemoryStore",
    "JsonlStore",
    "JsonlStoreConfig",
    "MemoryConfig",
    "configure_memory",
    "current_store",
]
