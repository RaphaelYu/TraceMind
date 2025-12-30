import json
from pathlib import Path
from typing import Dict

import pytest
from jsonschema import validate

from tm.artifacts.normalize import normalize_body

SCHEMAS_DIR = Path("tm/artifacts/schemas/v0")


def _load_schema(name: str) -> Dict[str, object]:
    return json.loads((SCHEMAS_DIR / name).read_text(encoding="utf-8"))


def _env_snapshot_example() -> Dict[str, object]:
    return {
        "snapshot_id": "env-123",
        "timestamp": "2025-01-01T00:00:00Z",
        "environment": {
            "host": "controller",
            "state": {"phase": "idle", "observers": ["video", "metrics"]},
        },
        "constraints": [{"type": "guard", "rule": "no-entropy", "description": "Stable data only"}],
        "data_hash": "hash-env-123",
    }


def _proposed_change_plan_example() -> Dict[str, object]:
    return {
        "plan_id": "plan-abc",
        "intent_id": "intent.perform.action",
        "decisions": [
            {
                "effect_ref": "resource:inventory:update",
                "target_state": {"count": 5},
                "idempotency_key": "plan-abc:resource:inventory:update",
                "reasoning_trace": "builtin.decide.plan",
            }
        ],
        "llm_metadata": {
            "model": "tm-llm/planner:0.1",
            "prompt_hash": "prompt-xyz",
            "determinism_hint": "deterministic",
        },
        "summary": "Replenish inventory",
        "policy_requirements": ["resource:inventory:update"],
    }


def _execution_report_example() -> Dict[str, object]:
    return {
        "report_id": "plan-abc",
        "artifact_refs": {"resource:inventory:update": {"count": 5, "status": "ok"}},
        "status": "succeeded",
        "policy_decisions": [{"effect_ref": "resource:inventory:update", "allowed": True, "reason": "allowlist"}],
        "errors": [],
        "artifacts": {
            "ObserveAgent": {"snapshot_hash": "hash-env-123"},
            "DecideAgent": {"plan_hash": "hash-plan-abc"},
            "ActAgent": {"log": "executed"},
        },
        "execution_hash": "hash-exec-1",
    }


@pytest.mark.parametrize(
    "schema_name, example",
    [
        ("env_snapshot.json", _env_snapshot_example()),
        ("proposed_change_plan.json", _proposed_change_plan_example()),
        ("execution_report.json", _execution_report_example()),
    ],
)
def test_controller_artifact_schemas_accept_examples(schema_name: str, example: Dict[str, object]) -> None:
    schema = _load_schema(schema_name)
    validate(example, schema)


def test_controller_artifact_body_normalization_is_deterministic() -> None:
    base_payload = _env_snapshot_example()
    variant_payload = {
        "constraints": base_payload["constraints"],
        "data_hash": base_payload["data_hash"],
        "environment": {
            "state": base_payload["environment"]["state"],
            "host": base_payload["environment"]["host"],
        },
        "snapshot_id": base_payload["snapshot_id"],
        "timestamp": base_payload["timestamp"],
    }
    assert normalize_body(base_payload) == normalize_body(variant_payload)
