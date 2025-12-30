from __future__ import annotations

from pathlib import Path
from typing import Mapping

import pytest

from tm.agents.models import AgentSpec
from tm.artifacts import Artifact, ArtifactEnvelope, ArtifactStatus, ArtifactType, verify
from tm.artifacts.models import ProposedChangePlanBody
from tm.controllers.decide.decide_agent import DecideAgent
from tm.controllers.decide.llm_record import LlmRecordStore


def _build_decide_agent_spec() -> AgentSpec:
    data = {
        "agent_id": DecideAgent.AGENT_ID,
        "name": "controller-decide",
        "version": "0.2",
        "runtime": {"kind": "python", "config": {}},
        "contract": {
            "inputs": [
                {
                    "ref": "state:env.snapshot",
                    "kind": "resource",
                    "schema": {"type": "object"},
                    "required": True,
                    "mode": "read",
                }
            ],
            "outputs": [
                {
                    "ref": "artifact:proposed.plan",
                    "kind": "artifact",
                    "schema": {"type": "object"},
                    "required": True,
                    "mode": "write",
                }
            ],
            "effects": [
                {
                    "name": "plan_decision",
                    "kind": "resource",
                    "target": "artifact:proposed.plan",
                    "idempotency": {"type": "keyed", "key_fields": ["plan_id"]},
                    "evidence": {"type": "hash", "path": "/plan"},
                }
            ],
        },
        "config_schema": {"type": "object"},
        "evidence_outputs": [{"name": "plan", "description": "record plan"}],
    }
    return AgentSpec.from_mapping(data)


def _snapshot_payload() -> Mapping[str, object]:
    return {
        "snapshot_id": "snapshot-1",
        "timestamp": "2025-01-01T00:00:00Z",
        "environment": {"state": {"phase": "test"}},
        "constraints": [],
        "data_hash": "hash-snapshot",
    }


def _assert_plan_verifiable(plan: Mapping[str, object]) -> None:
    envelope = ArtifactEnvelope(
        artifact_id="controller-plan/test",
        status=ArtifactStatus.CANDIDATE,
        artifact_type=ArtifactType.PROPOSED_CHANGE_PLAN,
        version="v0",
        created_by="tests",
        created_at="2025-01-01T00:00:00Z",
        body_hash="",
        envelope_hash="",
        meta={"phase": "controller-test"},
    )
    body = ProposedChangePlanBody.from_mapping(plan)
    artifact = Artifact(envelope=envelope, body_raw=plan, body=body)
    candidate, report = verify(artifact)
    assert candidate is not None
    assert not report.errors


@pytest.mark.parametrize("mode", ["live", "replay"])
def test_decide_agent_records_and_replays(tmp_path: Path, mode: str) -> None:
    spec = _build_decide_agent_spec()
    snapshot = _snapshot_payload()
    record_path = tmp_path / "decide-record.json"
    common_config = {
        "provider": "fake",
        "model": "fake-controller:0.1",
        "model_id": "tm-llm/controller",
        "model_version": "0.1",
        "intent_id": "intent.controller.demo",
        "summary": "Demo decide plan",
        "policy_requirements": ["resource:inventory:update"],
        "decisions": [
            {
                "effect_ref": "resource:inventory:update",
                "target_state": {"count": 5},
            }
        ],
        "record_path": str(record_path),
    }
    live_agent = DecideAgent(spec, common_config)
    live_output = live_agent.run({"state:env.snapshot": snapshot})
    assert "artifact:proposed.plan" in live_output
    live_plan = live_output["artifact:proposed.plan"]
    inputs_hash = live_plan["llm_metadata"]["inputs_hash"]
    assert inputs_hash
    _assert_plan_verifiable(live_plan)
    store = LlmRecordStore(record_path)
    stored_live_plan = store.get(inputs_hash)
    assert stored_live_plan == live_plan
    if mode == "live":
        return
    replay_agent = DecideAgent(spec, {**common_config, "mode": "replay"})
    replay_output = replay_agent.run({"state:env.snapshot": snapshot})
    assert replay_output["artifact:proposed.plan"] == live_plan
