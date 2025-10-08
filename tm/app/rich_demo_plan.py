from __future__ import annotations
from typing import Dict, Any
from tm.pipeline.engine import StepSpec, Rule, Plan

# ------------------ step functions ------------------


def step_validate_profile(ctx: Dict[str, Any]) -> Dict[str, Any]:
    new = ctx.get("new", {})
    if not new.get("nfInstanceId"):
        raise ValueError("nfInstanceId is required")
    if new.get("nfType") not in {"NRF", "AMF", "SMF", "UDM", "UPF"}:
        raise ValueError("nfType must be one of core NF types")
    return ctx


def step_normalize_services(ctx: Dict[str, Any]) -> Dict[str, Any]:
    new = dict(ctx.get("new", {}))
    services = new.get("services", [])
    for svc in services:
        name = (svc.get("name") or "").strip()
        svc["name"] = name
    ctx["new"] = new
    return ctx


def step_derive_status(ctx: Dict[str, Any]) -> Dict[str, Any]:
    new = dict(ctx.get("new", {}))
    states = [s.get("state") for s in new.get("services", [])]
    if states and all(s == "UP" for s in states):
        new["status"] = "ALIVE"
    elif any(s == "DOWN" for s in states):
        new["status"] = "DEGRADED"
    else:
        new["status"] = new.get("status", "REGISTERED")
    ctx["new"] = new
    ctx.setdefault("effects", []).append({"emit": "DerivedStatus", "value": new["status"]})
    return ctx


def step_stamp_version(ctx: Dict[str, Any]) -> Dict[str, Any]:
    new = dict(ctx.get("new", {}))
    meta = dict(new.get("meta", {}))
    meta["version"] = int(meta.get("version", 0)) + 1
    new["meta"] = meta
    ctx["new"] = new
    return ctx


def step_force_status_ok(ctx: Dict[str, Any]) -> Dict[str, Any]:
    # Intentionally writes to the same field as step_derive_status -> write-write potential
    new = dict(ctx.get("new", {}))
    new["status"] = "ALIVE"
    ctx["new"] = new
    return ctx


def step_dead_code(ctx: Dict[str, Any]) -> Dict[str, Any]:
    # Not referenced by any rule on purpose (unused)
    ctx.setdefault("effects", []).append({"emit": "DeadCode", "value": True})
    return ctx


# ------------------ build plan ------------------


def build_plan() -> Plan:
    steps = {
        "validate_profile": StepSpec(
            name="validate_profile", reads=["nfInstanceId", "nfType"], writes=[], fn=step_validate_profile
        ),
        "normalize_services": StepSpec(
            name="normalize_services", reads=["services[].name"], writes=["services[].name"], fn=step_normalize_services
        ),
        "derive_status": StepSpec(
            name="derive_status", reads=["status", "services[].state"], writes=["status"], fn=step_derive_status
        ),
        "stamp_version": StepSpec(
            name="stamp_version", reads=["meta.version"], writes=["meta.version"], fn=step_stamp_version
        ),
        "force_status_ok": StepSpec(
            name="force_status_ok", reads=["policy.forceAlive"], writes=["status"], fn=step_force_status_ok
        ),
        "dead_code_step": StepSpec(name="dead_code_step", reads=["unused"], writes=["unused"], fn=step_dead_code),
    }

    rules = [
        # Typical lifecycle: ensure profile validity first
        Rule(
            name="on_profile_change", triggers=["nfInstanceId", "nfType"], steps=["validate_profile", "stamp_version"]
        ),
        # Services changes -> normalize names then derive status
        Rule(
            name="on_services_change",
            triggers=["services[].state", "services[].name"],
            steps=["normalize_services", "derive_status"],
        ),
        # Manual status touches
        Rule(name="on_status_touch", triggers=["status"], steps=["stamp_version", "derive_status"]),
        # Policy may force status to ALIVE (conflicts with derive_status). Shares trigger head with on_status_touch
        Rule(name="on_policy_force", triggers=["status", "policy.forceAlive"], steps=["force_status_ok"]),
        # Suspicious: empty steps
        Rule(name="empty_rule_no_steps", triggers=["meta.note"], steps=[]),
        # Suspicious: empty triggers
        Rule(name="empty_rule_no_triggers", triggers=[], steps=["stamp_version"]),
    ]

    return Plan(steps=steps, rules=rules)
