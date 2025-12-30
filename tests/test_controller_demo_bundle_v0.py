from typing import Sequence

import pytest

from tm.artifacts.models import AgentBundleBody, Artifact, ArtifactEnvelope, ArtifactStatus, ArtifactType
from tm.controllers.builtins import ActMockAgent, DecideLLMStubAgent, ObserveMockAgent
from tm.runtime.executor import AgentBundleExecutor, AgentBundleExecutorError


def _io_ref(ref: str, kind: str = "resource", schema: dict | None = None, mode: str = "write") -> dict:
    return {
        "ref": ref,
        "kind": kind,
        "schema": schema or {"type": "object"},
        "required": True,
        "mode": mode,
    }


def _effect(name: str, target: str, key_fields: Sequence[str]) -> dict:
    return {
        "name": name,
        "kind": "resource",
        "target": target,
        "idempotency": {"type": "keyed", "key_fields": list(key_fields)},
        "evidence": {"type": "hash", "path": target},
    }


def _observe_agent_data() -> dict:
    return {
        "agent_id": ObserveMockAgent.AGENT_ID,
        "name": "controller-observe-mock",
        "version": "0.1",
        "runtime": {"kind": "python", "config": {}},
        "contract": {
            "inputs": [],
            "outputs": [_io_ref("state:env.snapshot", kind="resource")],
            "effects": [_effect("capture_snapshot", "state:env.snapshot", ["snapshot_id"])],
        },
        "config_schema": {"type": "object"},
        "evidence_outputs": [{"name": "snapshot", "description": "env snapshot evidence"}],
        "role": "observe",
    }


def _decide_agent_data() -> dict:
    return {
        "agent_id": DecideLLMStubAgent.AGENT_ID,
        "name": "controller-decide-mock",
        "version": "0.1",
        "runtime": {"kind": "python", "config": {}},
        "contract": {
            "inputs": [_io_ref("state:env.snapshot", kind="resource", mode="read")],
            "outputs": [_io_ref("artifact:proposed.plan", kind="artifact")],
            "effects": [_effect("plan_decision", "artifact:proposed.plan", ["plan_id"])],
        },
        "config_schema": {"type": "object"},
        "evidence_outputs": [{"name": "plan", "description": "decision plan evidence"}],
        "role": "decide",
    }


def _act_agent_data() -> dict:
    return {
        "agent_id": ActMockAgent.AGENT_ID,
        "name": "controller-act-mock",
        "version": "0.1",
        "runtime": {"kind": "python", "config": {}},
        "contract": {
            "inputs": [
                _io_ref("state:env.snapshot", kind="resource", mode="read"),
                _io_ref("artifact:proposed.plan", kind="artifact", mode="read"),
            ],
            "outputs": [
                _io_ref("artifact:execution.report", kind="artifact"),
                _io_ref("state:act.result", kind="resource"),
            ],
            "effects": [_effect("apply_inventory", "resource:inventory:update", ["idempotency_key"])],
        },
        "config_schema": {"type": "object"},
        "evidence_outputs": [{"name": "act_report", "description": "execution evidence"}],
        "role": "act",
    }


def _build_controller_bundle(policy_allow: Sequence[str] | None) -> Artifact:
    policy_meta = {"phase": "controller-demo"}
    if policy_allow is not None:
        policy_meta["policy"] = {"allow": list(policy_allow)}
    body_raw = {
        "bundle_id": "tm-controller/demo",
        "agents": [_observe_agent_data(), _decide_agent_data(), _act_agent_data()],
        "plan": [
            {
                "step": "observe",
                "agent_id": ObserveMockAgent.AGENT_ID,
                "phase": "run",
                "inputs": [],
                "outputs": ["state:env.snapshot"],
            },
            {
                "step": "decide",
                "agent_id": DecideLLMStubAgent.AGENT_ID,
                "phase": "run",
                "inputs": ["state:env.snapshot"],
                "outputs": ["artifact:proposed.plan"],
            },
            {
                "step": "act",
                "agent_id": ActMockAgent.AGENT_ID,
                "phase": "run",
                "inputs": ["state:env.snapshot", "artifact:proposed.plan"],
                "outputs": ["artifact:execution.report", "state:act.result"],
            },
        ],
        "meta": policy_meta,
    }
    body = AgentBundleBody.from_mapping(body_raw)
    envelope = ArtifactEnvelope(
        artifact_id="tm-controller/demo/bundle",
        status=ArtifactStatus.ACCEPTED,
        artifact_type=ArtifactType.AGENT_BUNDLE,
        version="v0",
        created_by="tests",
        created_at="2025-01-01T00:00:00Z",
        body_hash="bundle-body-hash",
        envelope_hash="bundle-envelope-hash",
        meta=dict(policy_meta),
    )
    return Artifact(envelope=envelope, body=body, body_raw=body_raw)


def test_controller_demo_policy_guard_blocks_when_allowlist_missing() -> None:
    bundle = _build_controller_bundle(None)
    executor = AgentBundleExecutor()
    with pytest.raises(AgentBundleExecutorError) as exc:
        executor.execute(bundle)
    assert "policy guard denied effect" in str(exc.value)


def test_controller_demo_bundle_runs_when_allowlist_present() -> None:
    bundle = _build_controller_bundle(["state:env.snapshot", "artifact:proposed.plan", "resource:inventory:update"])
    executor = AgentBundleExecutor()
    context = executor.execute(bundle)
    report = context.get_ref("artifact:execution.report")
    assert isinstance(report, dict)
    assert report["status"] == "succeeded"
    artifact_refs = report["artifact_refs"]
    assert "resource:inventory:update" in artifact_refs
    assert artifact_refs["resource:inventory:update"]["status"] == "applied"
    policy_decision = report["policy_decisions"][0]
    assert policy_decision["allowed"] is True
    assert policy_decision["reason"] == "allowlist"
    evidence_kinds = {entry.kind for entry in context.evidence.records()}
    assert {"builtin.observer.snapshot", "builtin.decide.plan", "builtin.act.report"}.issubset(evidence_kinds)
    assert context.metadata.get("executed_steps") == ["observe", "decide", "act"]
    assert context.get_ref("state:act.result")["status"] == "succeeded"
