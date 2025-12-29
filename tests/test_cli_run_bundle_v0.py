import argparse
import json
from pathlib import Path


from tm.agents.registry import register_agent, unregister_agent
from tm.agents.runtime import RuntimeAgent
from tm.cli.run_cli import _cmd_run_bundle


class DummyAgent(RuntimeAgent):
    def run(self, inputs):
        return {io_ref.ref: dict(inputs) for io_ref in self.contract.outputs}


def _bundle_payload(policy_allow: list[str] | None = None) -> dict:
    meta: dict = {"preconditions": ["artifact:config"]}
    if policy_allow is not None:
        meta["policy"] = {"allow": policy_allow}
    return {
        "envelope": {
            "artifact_id": "tm-agent-bundle-cli",
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
            "bundle_id": "tm-bundle/cli",
            "agents": [
                {
                    "agent_id": "tm-agent/cli:0.1",
                    "name": "cli",
                    "version": "0.1",
                    "runtime": {"kind": "tm-shell", "config": {"image": "cli:v0"}},
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
                    "evidence_outputs": [{"name": "result_hash"}],
                    "role": "executor",
                }
            ],
            "plan": [
                {
                    "step": "make",
                    "agent_id": "tm-agent/cli:0.1",
                    "phase": "run",
                    "inputs": ["artifact:config"],
                    "outputs": ["state:result"],
                }
            ],
            "meta": meta,
        },
    }


def _run_cli(args: argparse.Namespace) -> int:
    register_agent("tm-agent/cli:0.1", lambda spec, config: DummyAgent(spec, config))
    try:
        return _cmd_run_bundle(args)
    finally:
        unregister_agent("tm-agent/cli:0.1")


def test_run_cli_writes_yaml_report(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle.yaml"
    payload = _bundle_payload(policy_allow=["state:result"])
    bundle.write_text(json.dumps(payload), encoding="utf-8")
    report_path = tmp_path / "run-report.yaml"
    args = argparse.Namespace(
        bundle=str(bundle),
        inputs=['artifact:config={"payload":"value"}'],
        report=str(report_path),
        json=False,
    )
    rc = _run_cli(args)
    assert rc == 0
    text = report_path.read_text(encoding="utf-8")
    assert "success: true" in text


def test_run_cli_writes_json_report(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle.json"
    payload = _bundle_payload(policy_allow=["state:result"])
    bundle.write_text(json.dumps(payload), encoding="utf-8")
    report_path = tmp_path / "report.json"
    args = argparse.Namespace(
        bundle=str(bundle),
        inputs=['artifact:config={"payload":"value"}'],
        report=str(report_path),
        json=True,
    )
    rc = _run_cli(args)
    assert rc == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["success"]
    assert any(decision["allowed"] for decision in report["policy_decisions"])


def test_run_cli_reports_policy_denial(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle.yaml"
    payload = _bundle_payload(policy_allow=None)
    bundle.write_text(json.dumps(payload), encoding="utf-8")
    report_path = tmp_path / "report.yaml"
    args = argparse.Namespace(
        bundle=str(bundle),
        inputs=['artifact:config={"payload":"value"}'],
        report=str(report_path),
        json=False,
    )
    rc = _run_cli(args)
    assert rc == 1
    data = report_path.read_text(encoding="utf-8")
    assert "success: false" in data
    assert "allowed: false" in data
