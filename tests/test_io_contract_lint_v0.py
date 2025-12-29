import copy

from tm.artifacts.models import AgentBundleBody
from tm.lint import lint_agent_bundle_io_contract, lint_plan_io_contract


def _base_bundle_body() -> dict:
    return {
        "bundle_id": "tm-bundle/io",
        "agents": [
            {
                "agent_id": "tm-agent/runner:0.1",
                "name": "runner",
                "version": "0.1",
                "runtime": {"kind": "tm-shell", "config": {"image": "runner:v0"}},
                "contract": {
                    "inputs": [
                        {
                            "ref": "artifact:config",
                            "kind": "artifact",
                            "schema": "schemas/config-schema.json",
                            "required": True,
                            "mode": "read",
                        }
                    ],
                    "outputs": [
                        {
                            "ref": "state:workload",
                            "kind": "resource",
                            "schema": {"type": "object"},
                            "required": False,
                            "mode": "write",
                        }
                    ],
                    "effects": [
                        {
                            "name": "configure",
                            "kind": "resource",
                            "target": "state:workload",
                            "idempotency": {"type": "keyed", "key_fields": ["artifact_id"]},
                            "evidence": {"type": "hash", "path": "/state/config.hash"},
                        }
                    ],
                },
                "config_schema": {"type": "object"},
                "evidence_outputs": [{"name": "config_hash"}],
                "role": "initializer",
            }
        ],
        "plan": [
            {
                "step": "init",
                "agent_id": "tm-agent/runner:0.1",
                "phase": "init",
                "inputs": ["artifact:config"],
                "outputs": ["state:workload"],
            }
        ],
        "meta": {"preconditions": ["artifact:config"]},
    }


def test_agent_bundle_lint_accepts_valid_body():
    raw_body = _base_bundle_body()
    body = AgentBundleBody.from_mapping(copy.deepcopy(raw_body))
    issues = lint_agent_bundle_io_contract(body, raw_body)
    assert not issues


def test_agent_bundle_lint_requires_effects():
    raw_body = _base_bundle_body()
    raw_body["agents"][0]["contract"]["effects"].clear()
    body = AgentBundleBody.from_mapping(raw_body)
    issues = lint_agent_bundle_io_contract(body, raw_body)
    assert any(issue.code == "EFFECT_REQUIRED" for issue in issues)


def test_agent_bundle_lint_requires_idempotency_key():
    raw_body = _base_bundle_body()
    raw_body["agents"][0]["contract"]["effects"][0]["idempotency"]["key_fields"] = []
    body = AgentBundleBody.from_mapping(raw_body)
    issues = lint_agent_bundle_io_contract(body, raw_body)
    assert any(issue.code == "RESOURCE_IDEMPOTENCY" for issue in issues)


def test_agent_bundle_lint_enforces_plan_io_closure():
    raw_body = _base_bundle_body()
    raw_body["plan"][0]["inputs"] = ["artifact:missing"]
    body = AgentBundleBody.from_mapping(raw_body)
    issues = lint_agent_bundle_io_contract(body, raw_body)
    assert any(issue.code == "IO_CLOSURE" for issue in issues)


def test_plan_io_contract_lint_reports_effect_target_error():
    plan_body = {
        "plan_id": "plan-io",
        "owner": "team",
        "summary": "plan io contract",
        "steps": [],
        "io_contract": {
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
                    "ref": "state:record",
                    "kind": "resource",
                    "schema": {"type": "object"},
                    "required": False,
                    "mode": "write",
                }
            ],
            "effects": [
                {
                    "name": "finish",
                    "kind": "resource",
                    "target": "state:missing",
                    "idempotency": {"type": "keyed", "key_fields": ["artifact_id"]},
                    "evidence": {"type": "hash", "path": "/state/missing"},
                }
            ],
        },
    }
    issues = lint_plan_io_contract(plan_body)
    assert any(issue.code == "EFFECT_TARGET" for issue in issues)
