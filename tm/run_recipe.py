from __future__ import annotations

import asyncio
import time
import uuid
from pathlib import Path
from typing import Any, Dict

from tm.flow.recipe_loader import RecipeLoader, RecipeError
from tm.flow.runtime import FlowRuntime
from tm.flow.spec import FlowSpec
from tm.flow.flow import Flow


class RecipeFlow(Flow):
    def __init__(self, spec: FlowSpec) -> None:
        self._spec = spec

    @property
    def name(self) -> str:
        return self._spec.name

    def spec(self) -> FlowSpec:
        return self._spec


async def _run(spec: FlowSpec, inputs: Dict[str, Any]) -> Dict[str, Any]:
    runtime = FlowRuntime({spec.name: RecipeFlow(spec)})
    try:
        start = time.perf_counter()
        result = await runtime.run(spec.name, inputs=inputs)
        exec_ms = (time.perf_counter() - start) * 1000.0
        return {
            "status": result.get("status"),
            "run_id": result.get("run_id"),
            "output": result.get("output"),
            "exec_ms": exec_ms,
        }
    finally:
        await runtime.aclose()


def run_recipe(source: str | Path, inputs: Dict[str, Any] | None = None) -> Dict[str, Any]:
    loader = RecipeLoader()
    try:
        spec = loader.load(source)
        return asyncio.run(_run(spec, dict(inputs or {})))
    except (RecipeError, Exception) as exc:  # pragma: no cover - surface error
        return {
            "status": "error",
            "run_id": uuid.uuid4().hex,
            "output": {
                "error": str(exc),
            },
            "exec_ms": 0.0,
        }


__all__ = ["run_recipe"]
