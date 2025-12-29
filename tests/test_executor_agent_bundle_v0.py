import yaml
from pathlib import Path

import pytest

from tm.agents.registry import register_agent, unregister_agent
from tm.agents.runtime import RuntimeAgent
from tm.artifacts import load_yaml_artifact
from tm.runtime.context import ExecutionContext
from tm.runtime.executor import AgentBundleExecutor, AgentBundleExecutorError


class DummyAgent(RuntimeAgent):
    def run(self, inputs):
        outputs = {}
        for io_ref in self.contract.outputs:
            outputs[io_ref.ref] = {"input": dict(inputs)}
        return outputs


def _bundle_payload(policy_allow: list[str] | None = None) -> dict:
    meta = {"preconditions": ["artifact:config"]}
    if policy_allow is not None:
        meta["policy"] = {"allow": policy_allow}

    return {
        "envelope": {
            "artifact_id": "tm-agent-bundle-0002",
            "status": "accepted",
            "artifact_type": "agent_bundle",
            "version": "v0",
            "created_by": "tester",
            "created_at": "2024-01-01T00:00:00Z",
            "body_hash": "",
            "envelope_hash": "",
            "meta": {},
        },
        "body": {
            "bundle_id": "tm-bundle/executor",
            "agents": [
                {
                    "agent_id": "tm-agent/maker:0.1",
                    "name": "maker",
                    "version": "0.1",
                    "runtime": {"kind": "tm-shell", "config": {"image": "maker:v0"}},
                    "contract": {
                        "inputs": [
                            {
                                "ref": "artifact:config",
                                "kind": "artifact",
                                "schema": {"type": "object"},
                                "required": True,
                                "mode": "read",
                            }
                        ],
                        "outputs": [
                            {
                                "ref": "state:result",
                                "kind": "resource",
                                "schema": {"type": "object"},
                                "required": False,
                                "mode": "write",
                            }
                        ],
                        "effects": [
                            {
                                "name": "produce",
                                "kind": "resource",
                                "target": "state:result",
                                "idempotency": {"type": "keyed", "key_fields": ["artifact_id"]},
                                "evidence": {"type": "hash", "path": "/state/result.hash"},
                            }
                        ],
                    },
                    "config_schema": {"type": "object"},
                    "evidence_outputs": [{"name": "result_hash", "description": "hash of result"}],
                    "role": "executor",
                }
            ],
            "plan": [
                {
                    "step": "make",
                    "agent_id": "tm-agent/maker:0.1",
                    "phase": "run",
                    "inputs": ["artifact:config"],
                    "outputs": ["state:result"],
                }
            ],
            "meta": meta,
        },
    }


def test_executor_runs_agent_bundle(tmp_path: Path) -> None:
    payload = _bundle_payload(policy_allow=["state:result"])
    path = tmp_path / "bundle.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    artifact = load_yaml_artifact(path)
    register_agent("tm-agent/maker:0.1", lambda spec, config: DummyAgent(spec, config))
    try:
        ctx = ExecutionContext()
        ctx.set_ref("artifact:config", {"payload": "value"})
        executor = AgentBundleExecutor()
        result = executor.execute(artifact, context=ctx)
        assert result.get_ref("state:result") == {"input": {"artifact:config": {"payload": "value"}}}
        records = result.evidence.records()
        assert any(record.kind == "idempotency" for record in records)
        assert any(record.kind == "policy_guard" and record.payload["allowed"] for record in records)
        assert result.audits and result.audits[-1]["action"] == "policy_guard"
    finally:
        unregister_agent("tm-agent/maker:0.1")


def test_executor_rejects_invalid_artifact(tmp_path: Path) -> None:
    payload = _bundle_payload()
    payload["envelope"]["status"] = "candidate"
    path = tmp_path / "bundle.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    artifact = load_yaml_artifact(path)
    executor = AgentBundleExecutor()
    try:
        register_agent("tm-agent/maker:0.1", lambda spec, config: DummyAgent(spec, config))
        with pytest.raises(AgentBundleExecutorError):
            executor.execute(artifact)
    finally:
        unregister_agent("tm-agent/maker:0.1")


def test_executor_policy_guard_denies_resource(tmp_path: Path) -> None:
    payload = _bundle_payload(policy_allow=None)
    path = tmp_path / "bundle.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    artifact = load_yaml_artifact(path)
    register_agent("tm-agent/maker:0.1", lambda spec, config: DummyAgent(spec, config))
    try:
        ctx = ExecutionContext()
        ctx.set_ref("artifact:config", {"payload": "value"})
        executor = AgentBundleExecutor()
        with pytest.raises(AgentBundleExecutorError):
            executor.execute(artifact, context=ctx)
        records = [record for record in ctx.evidence.records() if record.kind == "policy_guard"]
        assert records
        assert not records[-1].payload["allowed"]
    finally:
        unregister_agent("tm-agent/maker:0.1")
