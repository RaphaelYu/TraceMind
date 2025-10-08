from __future__ import annotations

import asyncio
import inspect
import importlib
from typing import Any, Awaitable, Callable, Dict


class StepRegistry:
    """Minimal registry for reusable step callables."""

    def __init__(self) -> None:
        self._steps: Dict[str, Callable[..., Awaitable[Any] | Any]] = {}

    def register(self, name: str, func: Callable[..., Awaitable[Any] | Any]) -> None:
        if not isinstance(name, str) or not name:
            raise ValueError("Step name must be a non-empty string")
        if name in self._steps:
            raise ValueError(f"Step '{name}' already registered")
        self._steps[name] = func

    def resolve(self, reference: str) -> Callable[..., Awaitable[Any]]:
        if reference in self._steps:
            return self._wrap(self._steps[reference])
        return self._import_path(reference)

    def unregister(self, name: str) -> None:
        self._steps.pop(name, None)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _wrap(self, func: Callable[..., Awaitable[Any] | Any]) -> Callable[..., Awaitable[Any]]:
        async def runner(*args, **kwargs):
            if inspect.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, lambda: func(*args, **kwargs))

        return runner

    def _import_path(self, reference: str) -> Callable[..., Awaitable[Any]]:
        if not isinstance(reference, str) or ":" not in reference:
            raise KeyError(f"Unknown step reference '{reference}'")
        module_name, _, attr = reference.partition(":")
        if not module_name or not attr:
            raise KeyError(f"Invalid step reference '{reference}'")
        module = importlib.import_module(module_name)
        if not hasattr(module, attr):
            raise KeyError(f"Module '{module_name}' has no attribute '{attr}'")
        func = getattr(module, attr)
        if not callable(func):
            raise TypeError(f"Resolved attribute '{reference}' is not callable")
        return self._wrap(func)


step_registry = StepRegistry()


async def call(reference: str, *args, **kwargs) -> Any:
    runner = step_registry.resolve(reference)
    return await runner(*args, **kwargs)


__all__ = ["step_registry", "call"]
