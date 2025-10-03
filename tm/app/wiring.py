from __future__ import annotations
import os
from typing import List
from tm.io.http2_app import app, bus, svc, cfg  # reuse existing app & core objs
from tm.plugins.loader import load_plugins

# pipeline imports
from tm.pipeline.engine import Pipeline
from tm.pipeline.trace_store import PipelineTraceSink
from tm.pipeline.selectors import match as sel_match

# --- load plugins ---
PLUGINS = load_plugins()

# Merge plans from all plugins (simple concatenation)
from tm.pipeline.engine import Plan


def _merge_plans(plans: List[Plan]) -> Plan:
    steps = {}
    rules = []
    for p in plans:
        steps.update(p.steps)  # later plugins can override by name if desired
        rules.extend(p.rules)
    return Plan(steps=steps, rules=rules)

_plans = [plugin.build_plan() for plugin in PLUGINS]
_plans = [plan for plan in _plans if plan]
PLAN = _merge_plans(_plans) if _plans else Plan(steps={}, rules=[])

# subscribe plugin bus hooks
for plugin in PLUGINS:
    plugin.register_bus(bus, svc)

# --- Pipeline wiring (generic; io layer stays clean) ---
import time
from typing import Any, Tuple, List
Path = Tuple[Any, ...]

trace_sink = PipelineTraceSink(dir_path=os.path.join(cfg.data_dir, "trace"))
pipe = Pipeline(plan=PLAN, trace_sink=trace_sink.append)
_last: dict[str, dict] = {}

def _diff_json(old: Any, new: Any, path: Tuple[Any,...]=()) -> List[Tuple[Path, str, Any, Any]]:
    out: List[Tuple[Path, str, Any, Any]] = []
    if type(old) != type(new): out.append((path, 'modified', old, new)); return out
    if isinstance(old, dict):
        keys = set(old) | set(new)
        for k in sorted(keys):
            if k not in old: out.append((path+(k,), 'added', None, new[k]))
            elif k not in new: out.append((path+(k,), 'removed', old[k], None))
            else: out.extend(_diff_json(old[k], new[k], path+(k,)))
    elif isinstance(old, list):
        n = max(len(old), len(new))
        for i in range(n):
            if i >= len(old): out.append((path+(i,), 'added', None, new[i]))
            elif i >= len(new): out.append((path+(i,), 'removed', old[i], None))
            else: out.extend(_diff_json(old[i], new[i], path+(i,)))
    else:
        if old != new: out.append((path, 'modified', old, new))
    return out

def _on_event(ev: object):
    if ev.__class__.__name__ != "ObjectUpserted": return
    key = f"{ev.kind}:{ev.obj_id}"
    old = _last.get(key) or {}
    new = ev.payload or {}
    changes = _diff_json(old, new)
    changed_paths = [p for (p, _, __, ___) in changes]
    ctx = {"kind": ev.kind, "id": ev.obj_id, "old": old, "new": new, "effects": []}
    out = pipe.run(ctx, changed_paths, sel_match)
    _last[key] = out.get("new", new)

bus.subscribe(_on_event)

from tm.app.wiring_flows import router as flow_router
from tm.app.wiring_service import router as service_router
from tm.app.wiring_ai import router as ai_router
from tm.obs import counters
from tm.obs.exporters.prometheus import mount_prometheus
from tm.obs.exporters.file_exporter import maybe_enable_from_env as maybe_enable_file_exporter
from tm.obs.exporters.binlog_exporter import maybe_enable_from_env as maybe_enable_binlog_exporter
from tm.obs.exporters import get_exporter_factory

app.include_router(flow_router)
app.include_router(service_router)
app.include_router(ai_router)

exporters_env = os.getenv("TRACE_EXPORTERS")
requested = {item.strip() for item in exporters_env.split(",") if item.strip()} if exporters_env else {"prometheus", "file", "binlog"}

_active_exporters = []

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
    if factory:
        exporter = factory(counters.metrics)
        if exporter:
            exporter.start(counters.metrics)
            _active_exporters.append(exporter)
