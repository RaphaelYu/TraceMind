from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

from tm.dsl.runtime import Engine, PythonEngine

from .engine import get_engine
from .process_engine import ProcessEngine, ProcessEngineError, TransportError


@dataclass(frozen=True)
class RunResult:
    status: str
    state: Dict[str, Any]
    events: Tuple[Dict[str, Any], ...] = ()
    summary: Optional[Dict[str, Any]] = None


class IrRunnerError(RuntimeError):
    """Raised when an IR flow cannot be executed."""


def run_flow(
    flow_name: str,
    *,
    manifest_path: Path,
    inputs: Optional[Dict[str, Any]] = None,
    engine: Optional[Engine] = None,
) -> RunResult:
    manifest = _load_manifest(manifest_path)
    entry = _lookup_flow(manifest, flow_name)
    ir_path = (manifest_path.parent / entry["ir_path"]).resolve()
    ir = _load_json(ir_path)
    engine_to_use = engine or get_engine()

    if isinstance(engine_to_use, PythonEngine):
        return _run_with_python_engine(engine_to_use, ir, inputs or {})

    if isinstance(engine_to_use, ProcessEngine):
        return _run_with_process_engine(engine_to_use, ir, inputs or {})

    raise IrRunnerError(f"Unsupported engine type: {engine_to_use!r}")


# ------------------------------------------------------------------------------
# Python engine execution
# ------------------------------------------------------------------------------


def _run_with_python_engine(engine: PythonEngine, ir: Mapping[str, Any], inputs: Dict[str, Any]) -> RunResult:
    graph = ir.get("graph")
    if not isinstance(graph, Mapping):
        raise IrRunnerError("IR missing graph definition")
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise IrRunnerError("IR graph must contain nodes and edges arrays")

    node_map = {node["id"]: node for node in nodes if isinstance(node, Mapping) and "id" in node}
    if not node_map:
        raise IrRunnerError("IR contains no executable nodes")
    successors = _build_successors(edges)
    current = _find_entry_node(node_map.keys(), successors)

    state: Dict[str, Any] = dict(inputs)
    executed: set[str] = set()
    while current is not None:
        if current in executed:
            raise IrRunnerError(f"Cycle detected at node '{current}'")
        executed.add(current)
        node = node_map[current]
        ctx = _build_python_context(node)
        state = engine.run_step(ctx, state)
        current = successors.get(current)

    return RunResult(status="completed", state=state)


def _build_python_context(node: Mapping[str, Any]) -> Dict[str, Any]:
    node_id = node.get("id")
    node_type = node.get("type")
    params = node.get("with", {})
    ctx: Dict[str, Any] = {"step": node_id, "config": {}, "kind": node_type}

    if node_type == "switch":
        ctx["config"] = {
            "cases": params.get("cases", {}),
            "default": params.get("default"),
        }
    elif node_type == "dsl.emit":
        ctx["config"] = {"outputs": params}
    else:
        ctx["config"] = {"call": {"target": node_type, "args": params}}

    return ctx


def _build_successors(edges: Iterable[Mapping[str, Any]]) -> Dict[str, Optional[str]]:
    mapping: Dict[str, Optional[str]] = {}
    for edge in edges:
        src = edge.get("from")
        dst = edge.get("to")
        if isinstance(src, str) and isinstance(dst, str):
            mapping.setdefault(src, dst)
    return mapping


def _find_entry_node(nodes: Iterable[str], successors: Mapping[str, Optional[str]]) -> Optional[str]:
    candidates = set(nodes)
    for dst in successors.values():
        if dst in candidates:
            candidates.discard(dst)
    return next(iter(candidates), None)


# ------------------------------------------------------------------------------
# Process engine execution
# ------------------------------------------------------------------------------


def _run_with_process_engine(engine: ProcessEngine, ir: Mapping[str, Any], inputs: Dict[str, Any]) -> RunResult:
    run = engine.start_run(dict(ir), inputs, options={"run_id": inputs.get("run_id")})
    try:
        while True:
            payload = run.poll()
            status = payload.get("status")
            events = tuple(payload.get("events", []) or [])
            summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else None
            if status in {"completed", "failed"}:
                return RunResult(status=status or "unknown", state={"inputs": inputs}, events=events, summary=summary)
    except (ProcessEngineError, TransportError) as exc:
        raise IrRunnerError(f"Process engine run failed: {exc}") from exc
    finally:
        run.close()


# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------


def _load_manifest(path: Path) -> Any:
    if not path.exists():
        raise IrRunnerError(f"Manifest not found at {path}")
    return _load_json(path)


def _lookup_flow(manifest: Any, flow_name: str) -> Mapping[str, Any]:
    if not isinstance(manifest, list):
        raise IrRunnerError("Manifest must be a list of flow entries")
    for entry in manifest:
        if isinstance(entry, Mapping) and entry.get("name") == flow_name:
            return entry
    raise IrRunnerError(f"Flow '{flow_name}' not found in manifest")


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise IrRunnerError(f"Invalid JSON in {path}: {exc}") from exc
    except OSError as exc:
        raise IrRunnerError(f"Failed to read {path}: {exc}") from exc


__all__ = ["run_flow", "RunResult", "IrRunnerError"]
