from __future__ import annotations

import os
from typing import Any, List, Tuple

from tm.app.wiring_ai import router as ai_router
from tm.app.wiring_flows import router as flow_router
from tm.app.wiring_service import router as service_router
from tm.io.http2_app import app, bus, svc, cfg  # reuse existing app & core objs
from tm.obs import counters
from tm.obs.exporters import get_exporter_factory
from tm.obs.exporters.binlog_exporter import maybe_enable_from_env as maybe_enable_binlog_exporter
from tm.obs.exporters.file_exporter import maybe_enable_from_env as maybe_enable_file_exporter
from tm.obs.exporters.prometheus import mount_prometheus
from tm.pipeline.engine import Pipeline, Plan
from tm.pipeline.selectors import match as sel_match
from tm.pipeline.trace_store import PipelineTraceSink
from tm.plugins.loader import load_plugins

Path = Tuple[Any, ...]

# --- load plugins ---------------------------------------------------------
PLUGINS = load_plugins()


def _merge_plans(plans: List[Plan]) -> Plan:
    steps: dict[str, Any] = {}
    rules: list[Any] = []
    for plan in plans:
        steps.update(plan.steps)
        rules.extend(plan.rules)
    return Plan(steps=steps, rules=rules)


_loaded_plans = [plugin.build_plan() for plugin in PLUGINS]
_non_null_plans = [plan for plan in _loaded_plans if plan]
PLAN = _merge_plans(_non_null_plans) if _non_null_plans else Plan(steps={}, rules=[])

# subscribe plugin bus hooks
for plugin in PLUGINS:
    plugin.register_bus(bus, svc)


# --- Pipeline wiring (generic; io layer stays clean) ----------------------
TRACE_DIR = os.path.join(cfg.data_dir, "trace")
trace_sink = PipelineTraceSink(dir_path=TRACE_DIR)
pipe = Pipeline(plan=PLAN, trace_sink=trace_sink.append)
_last: dict[str, dict] = {}


def _diff_json(old: Any, new: Any, path: Path = ()) -> List[Tuple[Path, str, Any, Any]]:
    changes: List[Tuple[Path, str, Any, Any]] = []
    if type(old) is not type(new):
        changes.append((path, "modified", old, new))
        return changes

    if isinstance(old, dict):
        keys = set(old) | set(new)
        for key in sorted(keys):
            key_path = path + (key,)
            if key not in old:
                changes.append((key_path, "added", None, new[key]))
            elif key not in new:
                changes.append((key_path, "removed", old[key], None))
            else:
                changes.extend(_diff_json(old[key], new[key], key_path))
        return changes

    if isinstance(old, list):
        length = max(len(old), len(new))
        for index in range(length):
            index_path = path + (index,)
            if index >= len(old):
                changes.append((index_path, "added", None, new[index]))
            elif index >= len(new):
                changes.append((index_path, "removed", old[index], None))
            else:
                changes.extend(_diff_json(old[index], new[index], index_path))
        return changes

    if old != new:
        changes.append((path, "modified", old, new))
    return changes


def _on_event(ev: object) -> None:
    if ev.__class__.__name__ != "ObjectUpserted":
        return
    key = f"{ev.kind}:{ev.obj_id}"
    old_payload = _last.get(key) or {}
    new_payload = ev.payload or {}
    changes = _diff_json(old_payload, new_payload)
    changed_paths = [path for path, *_ in changes]
    ctx = {
        "kind": ev.kind,
        "id": ev.obj_id,
        "old": old_payload,
        "new": new_payload,
        "effects": [],
    }
    out = pipe.run(ctx, changed_paths, sel_match)
    _last[key] = out.get("new", new_payload)


bus.subscribe(_on_event)

# Routers ------------------------------------------------------------------
app.include_router(flow_router)
app.include_router(service_router)
app.include_router(ai_router)

# Exporters ----------------------------------------------------------------
requested_env = os.getenv("TRACE_EXPORTERS")
requested = (
    {item.strip() for item in requested_env.split(",") if item.strip()}
    if requested_env
    else {"prometheus", "file", "binlog"}
)

_active_exporters: list[Any] = []

if "prometheus" in requested:
    mount_prometheus(app, counters.metrics)
if "file" in requested:
    exporter = maybe_enable_file_exporter()
    if exporter:
        _active_exporters.append(exporter)
if "binlog" in requested:
    exporter = maybe_enable_binlog_exporter()
    if exporter:
        _active_exporters.append(exporter)

custom_names = requested.difference({"prometheus", "file", "binlog"})
for name in custom_names:
    factory = get_exporter_factory(name)
    if not factory:
        continue
    exporter = factory(counters.metrics)
    if exporter:
        exporter.start(counters.metrics)
        _active_exporters.append(exporter)


__all__ = ["PLAN", "pipe", "_diff_json"]
