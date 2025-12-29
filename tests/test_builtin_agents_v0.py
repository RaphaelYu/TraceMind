from __future__ import annotations

from pathlib import Path
from typing import Mapping

import yaml

from tm.agents import builtins  # noqa: F401 registers builtin runtime agents
from tm.artifacts import load_yaml_artifact
from tm.runtime.context import ExecutionContext
from tm.runtime.executor import AgentBundleExecutor


def _write_artifact(tmp_path: Path, payload: dict[str, object]):
    path = tmp_path / "bundle.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return load_yaml_artifact(path)


def _bundle_payload(
    agent_entry: dict[str, object],
    step_entry: dict[str, object],
    allowlist: list[str],
    preconditions: list[str],
) -> dict[str, object]:
    meta: dict[str, object] = {"preconditions": preconditions}
    if allowlist:
        meta["policy"] = {"allow": allowlist}

    return {
        "envelope": {
            "artifact_id": "tm-agent-bundle-builtins",
            "status": "accepted",
            "artifact_type": "agent_bundle",
            "version": "v0",
            "created_by": "test",
            "created_at": "2024-01-01T00:00:00Z",
            "body_hash": "",
            "envelope_hash": "",
            "meta": {},
        },
        "body": {
            "bundle_id": "tm-bundle/builtins",
            "agents": [agent_entry],
            "plan": [step_entry],
            "meta": meta,
        },
    }


def _execute_plan(
    payload: dict[str, object],
    context: ExecutionContext,
    tmp_path: Path,
    configs: Mapping[str, Mapping[str, object]] | None = None,
) -> ExecutionContext:
    artifact = _write_artifact(tmp_path, payload)
    executor = AgentBundleExecutor()
    return executor.execute(artifact, context=context, configs=configs)


def test_noop_agent_records_evidence(tmp_path: Path) -> None:
    agent_entry = {
        "agent_id": "tm-agent/noop:0.1",
        "name": "noop",
        "version": "0.1",
        "runtime": {"kind": "tm-noop", "config": {}},
        "contract": {
            "inputs": [
                {
                    "ref": "artifact:input",
                    "kind": "artifact",
                    "schema": {"type": "object"},
                    "required": True,
                    "mode": "read",
                }
            ],
            "outputs": [
                {
                    "ref": "state:noop.out",
                    "kind": "resource",
                    "schema": {"type": "object"},
                    "required": False,
                    "mode": "write",
                }
            ],
            "effects": [
                {
                    "name": "noop-effect",
                    "kind": "resource",
                    "target": "state:noop",
                    "idempotency": {"type": "reentrant"},
                    "evidence": {"type": "status"},
                }
            ],
        },
        "config_schema": {"type": "object"},
        "evidence_outputs": [{"name": "noop", "description": "noop evidence"}],
        "role": "builtin",
    }
    step_entry = {
        "step": "noop-step",
        "agent_id": "tm-agent/noop:0.1",
        "phase": "run",
        "inputs": ["artifact:input"],
        "outputs": ["state:noop.out"],
    }
    payload = _bundle_payload(agent_entry, step_entry, ["state:noop"], ["artifact:input"])
    context = ExecutionContext()
    context.set_ref("artifact:input", {"value": "input"})
    result = _execute_plan(payload, context, tmp_path)
    assert result.get_ref("state:noop.out") == {"value": "input"}
    builtin_records = [record for record in result.evidence.records() if record.kind == "builtin.noop"]
    assert builtin_records


def test_shell_agent_runs_command_and_captures_output(tmp_path: Path) -> None:
    agent_entry = {
        "agent_id": "tm-agent/shell:0.1",
        "name": "shell",
        "version": "0.1",
        "runtime": {"kind": "tm-shell", "config": {}},
        "contract": {
            "inputs": [
                {
                    "ref": "artifact:command",
                    "kind": "artifact",
                    "schema": {"type": ["string", "array"]},
                    "required": True,
                    "mode": "read",
                }
            ],
            "outputs": [
                {
                    "ref": "state:shell.stdout",
                    "kind": "resource",
                    "schema": {"type": "string"},
                    "required": False,
                    "mode": "write",
                },
                {
                    "ref": "state:shell.stderr",
                    "kind": "resource",
                    "schema": {"type": "string"},
                    "required": False,
                    "mode": "write",
                },
                {
                    "ref": "state:shell.exit_code",
                    "kind": "resource",
                    "schema": {"type": "integer"},
                    "required": False,
                    "mode": "write",
                },
            ],
            "effects": [
                {
                    "name": "execute-shell",
                    "kind": "resource",
                    "target": "state:shell.stdout",
                    "idempotency": {"type": "reentrant"},
                    "evidence": {"type": "status"},
                }
            ],
        },
        "config_schema": {"type": "object"},
        "evidence_outputs": [{"name": "shell"}],
        "role": "builtin",
    }
    step_entry = {
        "step": "shell-step",
        "agent_id": "tm-agent/shell:0.1",
        "phase": "run",
        "inputs": ["artifact:command"],
        "outputs": ["state:shell.stdout", "state:shell.stderr", "state:shell.exit_code"],
    }
    payload = _bundle_payload(agent_entry, step_entry, ["state:shell.stdout"], ["artifact:command"])
    context = ExecutionContext()
    context.set_ref("artifact:command", ["python3", "-c", "print('shell ok')"])
    result = _execute_plan(payload, context, tmp_path)
    stdout = result.get_ref("state:shell.stdout")
    stderr = result.get_ref("state:shell.stderr")
    exit_code = result.get_ref("state:shell.exit_code")
    assert isinstance(stdout, str) and stdout.strip() == "shell ok"
    assert stderr == ""
    assert exit_code == 0
    assert any(record.kind == "builtin.shell" for record in result.evidence.records())


def test_http_mock_returns_configured_response(tmp_path: Path) -> None:
    agent_entry = {
        "agent_id": "tm-agent/http-mock:0.1",
        "name": "http_mock",
        "version": "0.1",
        "runtime": {
            "kind": "tm-http-mock",
            "config": {
                "responses": {
                    "GET https://example.com/api": {
                        "status": 418,
                        "headers": {"x-test": "value"},
                        "body": "teapot",
                    }
                }
            },
        },
        "contract": {
            "inputs": [
                {
                    "ref": "artifact:http_request",
                    "kind": "artifact",
                    "schema": {"type": "object"},
                    "required": True,
                    "mode": "read",
                }
            ],
            "outputs": [
                {
                    "ref": "artifact:http_response",
                    "kind": "artifact",
                    "schema": {"type": "object"},
                    "required": False,
                    "mode": "write",
                }
            ],
            "effects": [
                {
                    "name": "mock-http",
                    "kind": "resource",
                    "target": "state:http.response",
                    "idempotency": {"type": "reentrant"},
                    "evidence": {"type": "status"},
                }
            ],
        },
        "config_schema": {"type": "object"},
        "evidence_outputs": [{"name": "http"}],
        "role": "builtin",
    }
    step_entry = {
        "step": "http-step",
        "agent_id": "tm-agent/http-mock:0.1",
        "phase": "run",
        "inputs": ["artifact:http_request"],
        "outputs": ["artifact:http_response"],
    }
    payload = _bundle_payload(agent_entry, step_entry, ["state:http.response"], ["artifact:http_request"])
    context = ExecutionContext()
    context.set_ref("artifact:http_request", {"method": "GET", "url": "https://example.com/api"})
    agent_config = agent_entry["runtime"]["config"]
    result = _execute_plan(
        payload,
        context,
        tmp_path,
        configs={"tm-agent/http-mock:0.1": agent_config},
    )
    response = result.get_ref("artifact:http_response")
    assert response["status"] == 418
    assert response["headers"]["x-test"] == "value"
    assert response["body"] == "teapot"
    assert any(record.kind == "builtin.http_mock" for record in result.evidence.records())
