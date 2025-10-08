from __future__ import annotations

from typing import Any, Dict, Optional

from tm.memory import current_store

STEP_NAME = "helpers.memory_set"


async def run(
    params: Dict[str, Any], *, flow_id: Optional[str] = None, step_id: Optional[str] = None
) -> Dict[str, Any]:
    session = str(params.get("session_id") or params.get("session") or "default")
    key = params.get("key")
    if not isinstance(key, str) or not key:
        return {"status": "error", "error_code": "BAD_REQUEST", "reason": "key required"}
    value = params.get("value")
    store = current_store()
    await store.set(session, key, value)
    return {"status": "ok", "value": value}


try:  # pragma: no cover
    from tm.steps.registry import register_step  # type: ignore

    register_step(STEP_NAME, run)
except Exception:
    pass
