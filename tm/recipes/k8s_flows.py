"""Reusable FlowSpec factories for Kubernetes-related automations."""

from __future__ import annotations

from typing import Dict, Optional

from tm.connectors.k8s import K8sClient
from tm.flow.correlate import CorrelationHub
from tm.flow.operations import Operation, ResponseMode
from tm.flow.spec import FlowSpec, StepDef


def pod_health_check(namespace: str, label_selector: Optional[str] = None) -> FlowSpec:
    """Build a flow that fetches pods and signals readiness via CorrelationHub."""

    spec = FlowSpec(name=f"k8s.pod_health_check.{namespace}")

    spec.add_step(
        StepDef(
            "build_req",
            Operation.TASK,
            next_steps=("fetch_pods",),
            config={
                "callable": _build_pod_request(namespace, label_selector),
                "response_mode": ResponseMode.DEFERRED.value,
            },
        )
    )
    spec.add_step(
        StepDef(
            "fetch_pods",
            Operation.TASK,
            next_steps=("signal",),
            config={"callable": _fetch_pods},
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


def restart_crashloop(namespace: str, pod_name: str) -> FlowSpec:
    """Build a flow that restarts a specific pod and signals completion."""

    spec = FlowSpec(name=f"k8s.restart_crashloop.{pod_name}")

    spec.add_step(
        StepDef(
            "build",
            Operation.TASK,
            next_steps=("restart",),
            config={
                "callable": _build_restart_request(namespace, pod_name),
                "response_mode": ResponseMode.DEFERRED.value,
            },
        )
    )
    spec.add_step(
        StepDef(
            "restart",
            Operation.TASK,
            next_steps=("signal",),
            config={"callable": _restart_pod},
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


# ---------------------------------------------------------------------------
# Step callables
# ---------------------------------------------------------------------------


def _build_pod_request(namespace: str, label_selector: Optional[str]):
    def _inner(ctx: Dict[str, object]) -> Dict[str, object]:
        params = dict(ctx.get("request", {}))
        params.update({"namespace": namespace})
        if label_selector:
            params["label_selector"] = label_selector
        ctx["request"] = params
        return ctx

    return _inner


def _fetch_pods(ctx: Dict[str, object]) -> Dict[str, object]:
    clients = ctx.get("clients") or {}
    client: K8sClient = clients.get("k8s")  # type: ignore[assignment]
    if client is None:
        raise ValueError("K8s client missing in ctx['clients']['k8s']")
    request_cfg = ctx.get("request", {})
    namespace = request_cfg.get("namespace")
    if not isinstance(namespace, str):
        raise ValueError("Namespace is required in ctx['request']['namespace']")
    label_selector = request_cfg.get("label_selector")
    pods = client.get_pods(namespace, label_selector if isinstance(label_selector, str) else None)
    ctx["result"] = pods
    return ctx


def _build_restart_request(namespace: str, pod_name: str):
    def _inner(ctx: Dict[str, object]) -> Dict[str, object]:
        ctx["request"] = {"namespace": namespace, "pod": pod_name}
        return ctx

    return _inner


def _restart_pod(ctx: Dict[str, object]) -> Dict[str, object]:
    clients = ctx.get("clients") or {}
    client: K8sClient = clients.get("k8s")  # type: ignore[assignment]
    if client is None:
        raise ValueError("K8s client missing in ctx['clients']['k8s']")
    cfg = ctx.get("request", {})
    namespace = cfg.get("namespace")
    pod = cfg.get("pod")
    if not isinstance(namespace, str) or not isinstance(pod, str):
        raise ValueError("Namespace and pod name required in ctx['request']")
    client.delete_pod(namespace, pod)
    ctx["result"] = {"namespace": namespace, "pod": pod, "action": "restart"}
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
