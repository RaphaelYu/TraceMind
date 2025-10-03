from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Dict


class DummyRuntime:
    def __init__(self) -> None:
        path = os.environ.get("TRACE_MIND_WORKER_RESULT_FILE")
        if not path:
            raise RuntimeError("TRACE_MIND_WORKER_RESULT_FILE env var not set")
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    async def run(self, flow_id: str, inputs: Dict[str, Any] | None = None) -> Dict[str, Any]:
        inputs = inputs or {}
        record = {"flow_id": flow_id, "inputs": inputs}
        # simple file append for trace; not async but OK for tests
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        await asyncio.sleep(0)
        return {"status": "ok", "output": inputs}

    async def aclose(self) -> None:
        await asyncio.sleep(0)


def build_runtime() -> DummyRuntime:
    return DummyRuntime()
