"""Executable handlers used by recipe documentation and tests."""

from __future__ import annotations

from typing import Any, Dict


def prepare(ctx: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    return dict(state or {})


def charge(ctx: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    data = dict(state or {})
    data["charged"] = True
    return data


def score(ctx: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    return dict(state or {})


def route(ctx: Dict[str, Any], state: Dict[str, Any]) -> str:
    if state.get("route") in {"manual", "auto"}:
        return state["route"]
    return "auto"


def risk_route(ctx: Dict[str, Any], state: Dict[str, Any]) -> str:
    decision = state.get("route")
    if decision in {"manual", "auto"}:
        return decision
    return "auto"


def manual_review(ctx: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    data = dict(state or {})
    data["manual_review"] = True
    return data


def auto_approve(ctx: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    data = dict(state or {})
    data["approved"] = True
    return data


def ingest(ctx: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    return {"document": state.get("document", "")}


def run_parallel(ctx: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    return dict(state or {})


def extract_text(ctx: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    return {"text": state.get("document", "").upper()}


def classify(ctx: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    return {"label": "default"}


def patch_payload(ctx: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    data = dict(state or {})
    data.setdefault("text", "")
    data.setdefault("label", "")
    return data
