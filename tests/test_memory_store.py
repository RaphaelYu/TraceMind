from pathlib import Path

import pytest

from tm.memory import MemoryConfig, configure_memory, current_store
from tm.memory.store import InMemoryStore, JsonlStore, JsonlStoreConfig


@pytest.mark.asyncio
async def test_in_memory_store_set_get_append():
    store = InMemoryStore()
    await store.set("sess", "key", 1)
    assert await store.get("sess", "key") == 1
    await store.append("sess", "key", 2)
    assert await store.get("sess", "key") == [1, 2]
    await store.clear("sess", "key")
    assert await store.get("sess", "key") is None


@pytest.mark.asyncio
async def test_jsonl_store_persistence(tmp_path: Path):
    path = tmp_path / "memory.jsonl"
    store = JsonlStore(JsonlStoreConfig(path=path))
    await store.set("sess", "key", {"a": 1})
    await store.append("sess", "log", "first")

    store2 = JsonlStore(JsonlStoreConfig(path=path))
    assert await store2.get("sess", "key") == {"a": 1}
    assert await store2.get("sess", "log") == ["first"]


@pytest.mark.asyncio
async def test_configure_memory_switches_backend(tmp_path: Path):
    configure_memory(MemoryConfig(backend="memory"))
    store = current_store()
    await store.set("session", "key", 1)
    assert isinstance(store, InMemoryStore)

    json_path = tmp_path / "mem.jsonl"
    configure_memory(MemoryConfig(backend="jsonl", path=str(json_path)))
    store = current_store()
    await store.set("session", "key", 2)
    assert await store.get("session", "key") == 2
    assert isinstance(store, JsonlStore)
