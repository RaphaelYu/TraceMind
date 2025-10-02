import pytest

from tm.memory import configure_memory, MemoryConfig
from tm.steps.memory_get import run as memory_get
from tm.steps.memory_set import run as memory_set
from tm.steps.memory_append import run as memory_append


@pytest.fixture(autouse=True)
def reset_memory(tmp_path):
    configure_memory(MemoryConfig(backend="jsonl", path=str(tmp_path / "mem.jsonl")))
    return None


@pytest.mark.asyncio
async def test_memory_set_and_get():
    await memory_set({"session_id": "s1", "key": "greeting", "value": "hello"})
    result = await memory_get({"session_id": "s1", "key": "greeting"})
    assert result["status"] == "ok"
    assert result["value"] == "hello"


@pytest.mark.asyncio
async def test_memory_append():
    await memory_append({"session_id": "s1", "key": "log", "item": "step1"})
    await memory_append({"session_id": "s1", "key": "log", "item": "step2"})
    result = await memory_get({"session_id": "s1", "key": "log"})
    assert result["value"] == ["step1", "step2"]
