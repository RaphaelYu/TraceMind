from __future__ import annotations

import pytest

from tm.flow.step_registry import call, step_registry


@pytest.mark.asyncio
async def test_register_and_call_sync_function():
    step_registry.unregister("sum")
    step_registry.register("sum", lambda a, b: a + b)
    result = await call("sum", 2, 3)
    assert result == 5


@pytest.mark.asyncio
async def test_call_imported_async_function():
    result = await call("tests.examples:multiply_async", 3, 4)
    assert result == 12


@pytest.mark.asyncio
async def test_unknown_reference_raises():
    step_registry.unregister("demo")
    with pytest.raises(KeyError):
        await call("demo", 1)
