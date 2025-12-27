import json
from pathlib import Path

from tm.cli.rerun import rerun_pipeline


def _intent_file(tmp_path: Path) -> Path:
    intent = {
        "intent_id": "intent.reference",
        "version": "1.0.0",
        "goal": {"type": "achieve", "target": "result.validated"},
    }
    path = tmp_path / "intent.json"
    path.write_text(json.dumps(intent), encoding="utf-8")
    return path


def _policy_file(tmp_path: Path) -> Path:
    policy = {
        "policy_id": "policy.reference",
        "version": "1.0.0",
        "state_schema": {
            "result.validated": {"type": "boolean"},
            "external.write.performed": {"type": "boolean"},
        },
        "invariants": [
            {
                "id": "inv.no_unvalidated_external_write",
                "type": "never",
                "condition": "external.write.performed && !result.validated",
            }
        ],
        "guards": [
            {
                "name": "external-write-approval",
                "type": "approval",
                "scope": "workflow",
                "required_for": ["external.write"],
            }
        ],
    }
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(policy), encoding="utf-8")
    return path


def _catalog_file(tmp_path: Path) -> Path:
    capabilities = [
        {
            "capability_id": "compute.process",
            "version": "1.0.0",
            "inputs": {},
            "outputs": {},
            "event_types": [{"name": "compute.process.done"}],
            "state_extractors": [
                {
                    "from_event": "compute.process.done",
                    "produces": {"prediction.ready": {"type": "boolean", "value": True}},
                }
            ],
            "safety_contract": {"determinism": True, "side_effects": [], "rollback": {"supported": True}},
        },
        {
            "capability_id": "validate.result",
            "version": "1.0.0",
            "inputs": {},
            "outputs": {},
            "event_types": [{"name": "validate.result.done"}],
            "state_extractors": [
                {
                    "from_event": "validate.result.done",
                    "produces": {
                        "result.validated": {"type": "boolean", "value": True},
                        "result.unvalidated": {"type": "boolean", "value": False},
                    },
                }
            ],
            "safety_contract": {"determinism": True, "side_effects": [], "rollback": {"supported": True}},
        },
        {
            "capability_id": "external.write",
            "version": "1.0.0",
            "inputs": {},
            "outputs": {},
            "event_types": [{"name": "external.write.done"}],
            "state_extractors": [
                {
                    "from_event": "external.write.done",
                    "produces": {"external.write.performed": {"type": "boolean", "value": True}},
                }
            ],
            "safety_contract": {"determinism": True, "side_effects": ["external_io"], "rollback": {"supported": False}},
        },
        {
            "capability_id": "case.create",
            "version": "1.0.0",
            "inputs": {},
            "outputs": {},
            "event_types": [{"name": "case.create.done"}],
            "state_extractors": [
                {
                    "from_event": "case.create.done",
                    "produces": {"case.created": {"type": "boolean", "value": True}},
                }
            ],
            "safety_contract": {"determinism": True, "side_effects": [], "rollback": {"supported": True}},
        },
        {
            "capability_id": "audit.record",
            "version": "1.0.0",
            "inputs": {},
            "outputs": {},
            "event_types": [{"name": "audit.record.done"}],
            "state_extractors": [
                {
                    "from_event": "audit.record.done",
                    "produces": {"audit.logged": {"type": "boolean", "value": True}},
                }
            ],
            "safety_contract": {"determinism": True, "side_effects": [], "rollback": {"supported": True}},
        },
    ]
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(capabilities), encoding="utf-8")
    return path


def test_rerun_pipeline_happy_path(tmp_path: Path) -> None:
    intent_path = _intent_file(tmp_path)
    policy_path = _policy_file(tmp_path)
    catalog_path = _catalog_file(tmp_path)
    payload = rerun_pipeline(
        intent_path=intent_path,
        policy_path=policy_path,
        catalog_path=catalog_path,
        mode="conservative",
        guard_decisions={"external-write-approval": True},
    )
    assert payload["intent"]["status"] == "OK"
    assert payload["verification"]["success"] is True
    assert payload["trace"]["violations"] == []
    assert payload["trace"]["metadata"]["guard_decisions"] == {"external-write-approval": True}
