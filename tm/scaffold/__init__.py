from __future__ import annotations

import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping, Optional

try:
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

PROJECT_CONFIG: Dict[str, Dict[str, object]] = {
    "runtime": {
        "flows_dir": "flows",
        "services_dir": "services",
        "max_concurrency": 100,
        "queue_capacity": 300,
    },
    "observability": {
        "exporters": ["file"],
    },
    "ai": {
        "tuner": "epsilon",
        "policy_endpoint": "",
    },
}


@dataclass
class ProjectContext:
    root: Path
    config: Dict[str, Dict[str, object]]

    @property
    def flows_dir(self) -> Path:
        return self.root / str(self.config["runtime"]["flows_dir"])

    @property
    def policies_dir(self) -> Path:
        return self.root / "policies"

    @property
    def services_dir(self) -> Path:
        return self.root / str(self.config["runtime"]["services_dir"])

    def write_config(self) -> None:
        content = _render_config(self.config)
        (self.root / "trace-mind.toml").write_text(content, encoding="utf-8")


def init_project(
    project_name: str,
    destination: Path | str,
    *,
    with_prom: bool = False,
    with_retrospect: bool = False,
) -> Path:
    dest = Path(destination).resolve()
    project_root = dest / project_name
    if project_root.exists() and any(project_root.iterdir()):
        raise FileExistsError(f"Destination '{project_root}' already exists and is not empty")
    project_root.mkdir(parents=True, exist_ok=True)

    config = _clone_config()
    exporters = list(config["observability"].get("exporters", []))
    if with_prom and "prom" not in exporters:
        exporters.append("prom")
    config["observability"]["exporters"] = exporters

    context = ProjectContext(project_root, config)
    _create_project_layout(context, with_prom=with_prom, with_retrospect=with_retrospect)
    context.write_config()
    return project_root


def create_flow(
    flow_name: str,
    *,
    project_root: Path | None = None,
    switch: bool = False,
    parallel: bool = False,
) -> Path:
    ctx = _load_project(project_root)
    ctx.flows_dir.mkdir(parents=True, exist_ok=True)
    (ctx.flows_dir / "__init__.py").touch(exist_ok=True)

    filename = f"{_slug(flow_name)}.py"
    path = ctx.flows_dir / filename
    if path.exists():
        raise FileExistsError(f"Flow file '{path}' already exists")

    template = _flow_template(flow_name, switch=switch, parallel=parallel)
    path.write_text(template, encoding="utf-8")
    return path


def create_policy(
    policy_name: str,
    *,
    project_root: Path | None = None,
    strategy: str = "epsilon",
    mcp_endpoint: Optional[str] = None,
) -> Path:
    ctx = _load_project(project_root)
    policies_dir = ctx.policies_dir
    policies_dir.mkdir(parents=True, exist_ok=True)
    (policies_dir / "__init__.py").touch(exist_ok=True)

    filename = f"{_slug(policy_name)}.py"
    path = policies_dir / filename
    if path.exists():
        raise FileExistsError(f"Policy file '{path}' already exists")

    template = _policy_template(policy_name, strategy=strategy, mcp_endpoint=mcp_endpoint)
    path.write_text(template, encoding="utf-8")

    if mcp_endpoint is not None:
        ctx.config.setdefault("ai", {})
        ctx.config["ai"]["policy_endpoint"] = mcp_endpoint
        ctx.write_config()

    return path


def create_service(
    service_name: str,
    *,
    project_root: Path | None = None,
    flow_name: str = "hello",
) -> Path:
    ctx = _load_project(project_root)
    services_dir = ctx.services_dir
    services_dir.mkdir(parents=True, exist_ok=True)
    (services_dir / "__init__.py").touch(exist_ok=True)

    filename = f"{_slug(service_name)}.py"
    path = services_dir / filename
    if path.exists():
        raise FileExistsError(f"Service file '{path}' already exists")

    template = _service_template(service_name, flow_name)
    path.write_text(template, encoding="utf-8")
    return path


def find_project_root(start: Path | None = None) -> Path:
    start_path = Path(start or Path.cwd()).resolve()
    for candidate in [start_path] + list(start_path.parents):
        if (candidate / "trace-mind.toml").exists():
            return candidate
    raise FileNotFoundError("trace-mind.toml not found in current directory or parents")


def _load_project(root: Path | None) -> ProjectContext:
    project_root = find_project_root(root)
    config_path = project_root / "trace-mind.toml"
    if not config_path.exists():
        raise FileNotFoundError(f"Missing trace-mind.toml at {config_path}")
    with config_path.open("rb") as fh:
        config = tomllib.load(fh)
    return ProjectContext(project_root, config)


def _clone_config() -> Dict[str, Dict[str, object]]:
    return {
        section: {
            key: (value[:] if isinstance(value, list) else value)
            for key, value in fields.items()
        }
        for section, fields in PROJECT_CONFIG.items()
    }


def _render_config(config: Mapping[str, Mapping[str, object]]) -> str:
    exporters = config["observability"].get("exporters", [])
    exporters_repr = ", ".join(f'"{value}"' for value in exporters)
    lines = [
        "[runtime]",
        f'flows_dir = "{config["runtime"]["flows_dir"]}"',
        f'services_dir = "{config["runtime"]["services_dir"]}"',
        f'max_concurrency = {config["runtime"]["max_concurrency"]}',
        f'queue_capacity = {config["runtime"]["queue_capacity"]}',
        "",
        "[observability]",
        f"exporters = [{exporters_repr}]",
        "",
        "[ai]",
        f'tuner = "{config["ai"].get("tuner", "epsilon")}"',
        f'policy_endpoint = "{config["ai"].get("policy_endpoint", "")}"',
        "",
    ]
    return "\n".join(lines)


def _create_project_layout(
    context: ProjectContext,
    *,
    with_prom: bool,
    with_retrospect: bool,
) -> None:
    flows_dir = context.flows_dir
    flows_dir.mkdir(parents=True, exist_ok=True)
    (flows_dir / "__init__.py").touch(exist_ok=True)
    (flows_dir / "hello.py").write_text(
        _flow_template("hello", switch=False, parallel=False),
        encoding="utf-8",
    )

    policies_dir = context.policies_dir
    policies_dir.mkdir(parents=True, exist_ok=True)
    (policies_dir / "__init__.py").touch(exist_ok=True)
    (policies_dir / "default_policy.py").write_text(
        _policy_template("default_policy", strategy="epsilon", mcp_endpoint=""),
        encoding="utf-8",
    )

    services_dir = context.services_dir
    services_dir.mkdir(parents=True, exist_ok=True)
    (services_dir / "__init__.py").touch(exist_ok=True)
    (services_dir / "sample_service.py").write_text(
        _service_template("sample_service", "hello"),
        encoding="utf-8",
    )

    exporters_dir = context.root / "exporters"
    exporters_dir.mkdir(parents=True, exist_ok=True)
    (exporters_dir / "__init__.py").touch(exist_ok=True)
    (exporters_dir / "file_exporter.py").write_text(_EXPORTER_TEMPLATE, encoding="utf-8")

    if with_retrospect:
        (exporters_dir / "retrospect_exporter.py").write_text(_RETROSPECT_TEMPLATE, encoding="utf-8")

    if with_prom:
        hooks_dir = context.root / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        (hooks_dir / "__init__.py").touch(exist_ok=True)
        (hooks_dir / "metrics_trace.py").write_text(_PROM_HOOK_TEMPLATE, encoding="utf-8")

    scripts_dir = context.root / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    run_script = scripts_dir / "run_local.sh"
    run_script.write_text(_RUN_SCRIPT_TEMPLATE, encoding="utf-8")
    _make_executable(run_script)

    (context.root / "README.md").write_text(_README_TEMPLATE, encoding="utf-8")


def _make_executable(path: Path) -> None:
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _flow_template(flow_name: str, *, switch: bool, parallel: bool) -> str:
    class_name = f"{_camel(flow_name)}Flow"
    flow_id = _slug(flow_name)
    if switch:
        body = _FLOW_SWITCH_BODY
    elif parallel:
        body = _FLOW_PARALLEL_BODY
    else:
        body = _FLOW_BASIC_BODY
    return _FLOW_TEMPLATE.format(
        class_name=class_name,
        flow_id=flow_id,
        flow_name=flow_name,
        body=body,
    )


def _policy_template(policy_name: str, *, strategy: str, mcp_endpoint: Optional[str]) -> str:
    class_name = _camel(policy_name)
    slug = _slug(policy_name)
    if strategy == "ucb":
        body_init = _POLICY_UCB_INIT
        body_choose = _POLICY_UCB_CHOOSE
        body_update = _POLICY_UCB_UPDATE
        params = "confidence: float = 2.0"
    else:
        body_init = _POLICY_EPSILON_INIT
        body_choose = _POLICY_EPSILON_CHOOSE
        body_update = _POLICY_EPSILON_UPDATE
        params = "epsilon: float = 0.1"
    endpoint_line = f"POLICY_ENDPOINT = \"{mcp_endpoint}\"" if mcp_endpoint else "POLICY_ENDPOINT = \"\""
    return _POLICY_TEMPLATE.format(
        class_name=class_name,
        slug=slug,
        params=params,
        body_init=body_init,
        body_choose=body_choose,
        body_update=body_update,
        policy_endpoint=endpoint_line,
    )


def _service_template(service_name: str, flow_name: str) -> str:
    class_name = _camel(service_name)
    flow_slug = _slug(flow_name)
    return _SERVICE_TEMPLATE.format(class_name=class_name, flow_slug=flow_slug)


def _slug(value: str) -> str:
    safe = []
    for ch in value:
        if ch.isalnum() or ch in {"-", "_"}:
            safe.append(ch.lower())
        else:
            safe.append("-")
    result = "".join(safe).strip("-")
    return result or "sample"


def _camel(value: str) -> str:
    parts = _slug(value).replace("-", "_").split("_")
    return "".join(part.capitalize() for part in parts if part)


_FLOW_TEMPLATE = """"""Flow definition for {flow_name}."""
from __future__ import annotations

from typing import Any, Dict

from tm.flow.flow import Flow
from tm.flow.operations import Operation
from tm.flow.spec import FlowSpec, StepDef


class {class_name}(Flow):
    @property
    def name(self) -> str:
        return "{flow_id}"

    def spec(self) -> FlowSpec:
        return self._build_spec()

    def _build_spec(self) -> FlowSpec:
        spec = FlowSpec(name=self.name)
{body}
        return spec


async def before_task(ctx: Dict[str, Any]) -> None:
    ctx.setdefault("log", []).append("before_task")


async def after_task(ctx: Dict[str, Any], output: Dict[str, Any]) -> None:
    ctx.setdefault("log", []).append("after_task")


async def run_task(ctx: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    state = dict(state or {})
    state.setdefault("message", f"Hello from {flow_id}")
    return state


FLOW = {class_name}()
"""

_FLOW_BASIC_BODY = """        spec.add_step(
            StepDef(
                "start",
                Operation.TASK,
                next_steps=("finish",),
                before=before_task,
                run=run_task,
                after=after_task,
            )
        )
        spec.add_step(StepDef("finish", Operation.FINISH))
"""

_FLOW_SWITCH_BODY = """        spec.add_step(
            StepDef(
                "start",
                Operation.TASK,
                next_steps=("route",),
                before=before_task,
                run=run_task,
                after=after_task,
            )
        )
        spec.add_step(
            StepDef(
                "route",
                Operation.SWITCH,
                next_steps=("left", "right"),
                config={{"key": "branch", "default": "left"}},
            )
        )
        spec.add_step(StepDef("left", Operation.TASK, next_steps=("finish",)))
        spec.add_step(StepDef("right", Operation.TASK, next_steps=("finish",)))
        spec.add_step(StepDef("finish", Operation.FINISH))
"""

_FLOW_PARALLEL_BODY = """        spec.add_step(
            StepDef(
                "start",
                Operation.TASK,
                next_steps=("fan_out",),
                before=before_task,
                run=run_task,
                after=after_task,
            )
        )
        spec.add_step(
            StepDef(
                "fan_out",
                Operation.PARALLEL,
                next_steps=("finish",),
                config={{"branches": ["branch_a", "branch_b"]}},
            )
        )
        spec.add_step(StepDef("branch_a", Operation.TASK, next_steps=("finish",)))
        spec.add_step(StepDef("branch_b", Operation.TASK, next_steps=("finish",)))
        spec.add_step(StepDef("finish", Operation.FINISH))
"""

_POLICY_TEMPLATE = """"""Policy skeleton for {slug}."""
from __future__ import annotations

import random
from typing import Any, Mapping, Sequence

{policy_endpoint}

class {class_name}Policy:
    def __init__(self, {params}) -> None:
{body_init}

    def choose(self, binding: str, candidates: Sequence[str], context: Mapping[str, Any]) -> str:
{body_choose}

    def update(self, binding: str, arm: str, reward: float, context: Mapping[str, Any]) -> None:
{body_update}

"""

_POLICY_EPSILON_INIT = "        self.epsilon = epsilon\n        self._scores: dict[str, float] = {}\n"

_POLICY_UCB_INIT = (
    "        self.confidence = confidence\n"
    "        self._pulls: dict[str, int] = {}\n"
    "        self._scores: dict[str, float] = {}\n"
)

_POLICY_EPSILON_CHOOSE = "        if not candidates:\n            raise ValueError(\"No candidates provided\")\n        for arm in candidates:\n            self._scores.setdefault(arm, 0.0)\n        if random.random() < self.epsilon:\n            return random.choice(list(candidates))\n        return max(candidates, key=self._scores.get)\n"

_POLICY_UCB_CHOOSE = (
    "        if not candidates:\n            raise ValueError(\"No candidates provided\")\n        import math\n\n        for arm in candidates:\n            self._pulls.setdefault(arm, 0)\n            self._scores.setdefault(arm, 0.0)\n        total = sum(self._pulls.values()) + 1\n\n        def score(arm: str) -> float:\n            bonus = math.sqrt(2 * math.log(total + 1) / (self._pulls[arm] + 1))\n            return self._scores[arm] + self.confidence * bonus\n\n        return max(candidates, key=score)\n"
)

_POLICY_EPSILON_UPDATE = "        current = self._scores.get(arm, 0.0)\n        self._scores[arm] = current + 0.1 * (reward - current)\n"

_POLICY_UCB_UPDATE = (
    "        pulls = self._pulls.get(arm, 0) + 1\n        current = self._scores.get(arm, 0.0)\n        self._pulls[arm] = pulls\n        self._scores[arm] = current + (reward - current) / pulls\n"
)

_SERVICE_TEMPLATE = """"""Service binding skeleton."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from tm.flow.operations import ResponseMode
from tm.service import BindingRule, BindingSpec, Operation, ServiceBody
from tm.service.router import OperationRouter
from tm.model.spec import FieldSpec, ModelSpec

router = APIRouter(prefix="/{class_name}", tags=["{class_name}"])

model_spec = ModelSpec(
    name="{class_name}",
    fields=(
        FieldSpec(name="id", type="string"),
        FieldSpec(name="data", type="object", required=False, default={{}}),
    ),
    allow_extra=True,
)

binding = BindingSpec(
    model=model_spec.name,
    rules=[BindingRule(operation=Operation.READ, flow_name="{flow_slug}")],
)

service_body = ServiceBody(
    model=model_spec,
    runtime=None,  # Inject FlowRuntime when wiring application
    binding=binding,
    router=None,
)

@router.post("/run")
async def run_service(payload: dict) -> dict:
    if payload.get("model") != model_spec.name:
        raise HTTPException(status_code=404, detail="Unknown model")
    result = await service_body.handle(Operation.READ, payload.get("payload", {{}}), response_mode=ResponseMode.DEFERRED)
    return result

"""

_EXPORTER_TEMPLATE = """"""File exporter placeholder."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable


class FileExporter:
    def export(self, records: Iterable[dict], *, output_dir: str) -> Path:
        path = Path(output_dir) / "records.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            for record in records:
                fh.write(str(record) + "\n")
        return path

"""

_RETROSPECT_TEMPLATE = """from __future__ import annotations

from pathlib import Path
from typing import Iterable

from tm.obs.retrospect import load_window


def export_recent_metrics(dir_path: str, window_seconds: int = 300) -> Iterable[dict]:
    """Example Retrospect usage."""
    return load_window(str(Path(dir_path)), 0, window_seconds)
"""

_PROM_HOOK_TEMPLATE = """from __future__ import annotations

from prometheus_client import Counter

TRACE_EVENTS = Counter("trace_events_total", "Flow trace events", ["flow", "status"])


def on_event(flow: str, status: str) -> None:
    TRACE_EVENTS.labels(flow=flow, status=status).inc()
"""

_RUN_SCRIPT_TEMPLATE = """#!/usr/bin/env bash
set -euo pipefail

python -m tm.app.wiring_flows "$@"
"""

_README_TEMPLATE = """# TraceMind Project Scaffold

This project was generated by `tm init`.

```bash
pip install -e .
python scripts/run_local.sh
```

Directory layout:

- `flows/` – custom flow definitions.
- `policies/` – policy hooks.
- `services/` – API bindings.
- `exporters/` – observability exporters.
- `scripts/run_local.sh` – local execution helper.
"""


__all__ = [
    "create_flow",
    "create_policy",
    "create_service",
    "find_project_root",
    "init_project",
]
