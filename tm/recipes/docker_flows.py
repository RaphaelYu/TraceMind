"""FlowSpec factories for Docker interactions."""

from __future__ import annotations

from typing import Dict, List

from tm.connectors.docker import DockerClient
from tm.flow.correlate import CorrelationHub
from tm.flow.operations import Operation, ResponseMode
from tm.flow.spec import FlowSpec, StepDef


def container_health(container_names: List[str]) -> FlowSpec:
    spec = FlowSpec(name="docker.container_health")
    spec.add_step(
        StepDef(
            "build",
            Operation.TASK,
            next_steps=("list",),
            config={
                "callable": _build_health_request(container_names),
                "response_mode": ResponseMode.DEFERRED.value,
            },
        )
    )
    spec.add_step(
        StepDef(
            "list",
            Operation.TASK,
            next_steps=("signal",),
            config={"callable": _list_containers},
        )
    )
    spec.add_step(
        StepDef(
            "signal",
            Operation.TASK,
            next_steps=(),
            config={"callable": _signal_ready},
        )
    )
    return spec


def restart_container(container_name: str) -> FlowSpec:
    spec = FlowSpec(name=f"docker.restart.{container_name}")
    spec.add_step(
        StepDef(
            "build",
            Operation.TASK,
            next_steps=("restart",),
            config={
                "callable": _build_restart_request(container_name),
                "response_mode": ResponseMode.DEFERRED.value,
            },
        )
    )
    spec.add_step(
        StepDef(
            "restart",
            Operation.TASK,
            next_steps=("signal",),
            config={"callable": _restart_container},
        )
    )
    spec.add_step(
        StepDef(
            "signal",
            Operation.TASK,
            next_steps=(),
            config={"callable": _signal_ready},
        )
    )
    return spec


def _build_health_request(names: List[str]):
    def _inner(ctx: Dict[str, object]) -> Dict[str, object]:
        ctx["request"] = {"names": list(names)}
        return ctx

    return _inner


def _list_containers(ctx: Dict[str, object]) -> Dict[str, object]:
    clients = ctx.get("clients") or {}
    client: DockerClient = clients.get("docker")  # type: ignore[assignment]
    if client is None:
        raise ValueError("Docker client missing in ctx['clients']['docker']")
    names = ctx.get("request", {}).get("names", [])
    containers = client.list_containers(all=True) or []
    if isinstance(names, list) and names:
        selected = [c for c in containers if c.get("Names") and any(n in c.get("Names", []) for n in names)]
    else:
        selected = containers
    ctx["result"] = {"containers": selected}
    return ctx


def _build_restart_request(name: str):
    def _inner(ctx: Dict[str, object]) -> Dict[str, object]:
        ctx["request"] = {"container": name}
        return ctx

    return _inner


def _restart_container(ctx: Dict[str, object]) -> Dict[str, object]:
    clients = ctx.get("clients") or {}
    client: DockerClient = clients.get("docker")  # type: ignore[assignment]
    if client is None:
        raise ValueError("Docker client missing in ctx['clients']['docker']")
    container = ctx.get("request", {}).get("container")
    if not isinstance(container, str):
        raise ValueError("Container name required in ctx['request']['container']")
    success = client.restart(container)
    ctx["result"] = {"container": container, "restarted": success}
    return ctx


def _signal_ready(ctx: Dict[str, object]) -> Dict[str, object]:
    hub: CorrelationHub = ctx.get("correlator")  # type: ignore[assignment]
    if hub is None:
        raise ValueError("correlator must be provided in ctx['correlator']")
    req_id = ctx.get("req_id")
    if not isinstance(req_id, str):
        raise ValueError("req_id must be provided in ctx['req_id']")
    payload = {"status": "ready", "data": ctx.get("result")}
    hub.signal(req_id, payload)
    ctx["response"] = payload
    return ctx
