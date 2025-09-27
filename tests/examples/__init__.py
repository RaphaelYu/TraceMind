"""Example handlers used by recipe loader tests."""

from __future__ import annotations

from typing import Any, Dict


async def noop_before(ctx: Dict[str, Any]) -> None:  # pragma: no cover - placeholder
    ctx.setdefault("log", []).append("before")


def prepare(ctx: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    return dict(state or {})


def charge(ctx: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    state = dict(state or {})
    state["charged"] = True
    return state


def manual_review(ctx: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    state = dict(state or {})
    state["reviewed"] = True
    return state


def auto_approve(ctx: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    state = dict(state or {})
    state["approved"] = True
    return state


def risk_route(ctx: Dict[str, Any], state: Dict[str, Any]) -> str:
    return state.get("route", "auto")


def ingest(ctx: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    return {"document": state.get("document", "")}


def run_parallel(ctx: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    return state


def extract_text(ctx: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    return {"text": state.get("document", "").upper()}


def classify(ctx: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    return {"label": "default"}


def patch_payload(ctx: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    data = dict(state or {})
    data.setdefault("text", "")
    data.setdefault("label", "")
    return data


def add(a: int, b: int) -> int:
    return a + b


async def multiply_async(a: int, b: int) -> int:
    return a * b
