"""Recipe-only template step implementations."""

from __future__ import annotations

from typing import Any, Dict

def hello_greet(ctx: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    name = state.get("name") or "world"
    return {"message": f"Hello, {name}!"}
