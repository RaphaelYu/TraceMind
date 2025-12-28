from pathlib import Path

import yaml

from tm.artifacts import ConsistencyCode, check_consistency, load_yaml_artifact, verify
from tm.artifacts.registry import ArtifactRegistry, RegistryStorage


def _write_artifact(tmp_path: Path, data: dict[str, object], name: str) -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def _verify_and_register(path: Path, registry: ArtifactRegistry):
    artifact = load_yaml_artifact(path)
    accepted, _ = verify(artifact)
    assert accepted is not None
    registry.add(accepted, path)
    return accepted


def _load_and_verify(path: Path):
    artifact = load_yaml_artifact(path)
    accepted, _ = verify(artifact)
    assert accepted is not None
    return accepted


def _base_intent_artifact() -> dict[str, object]:
    return {
        "envelope": {
            "artifact_id": "tm-intent-0001",
            "status": "candidate",
            "artifact_type": "intent",
            "version": "v0",
            "created_by": "tester",
            "created_at": "2024-01-01T00:00:00Z",
            "body_hash": "",
            "envelope_hash": "",
            "meta": {},
        },
        "body": {
            "intent_id": "TM-INT-0001",
            "title": "Intent",
            "context": "Test context",
            "goal": "Reach the destination",
            "non_goals": [],
            "actors": [],
            "inputs": [],
            "outputs": [],
            "constraints": [],
            "success_metrics": [],
            "risks": [],
            "assumptions": [],
            "trace_links": {"related_intents": []},
        },
    }


def _base_plan_artifact() -> dict[str, object]:
    return {
        "envelope": {
            "artifact_id": "tm-plan-0001",
            "status": "candidate",
            "artifact_type": "plan",
            "version": "v0",
            "created_by": "tester",
            "created_at": "2024-01-01T00:00:00Z",
            "body_hash": "",
            "envelope_hash": "",
            "meta": {},
        },
        "body": {
            "plan_id": "plan-abc",
            "owner": "team",
            "summary": "execute steps",
            "steps": [
                {"name": "step-one", "reads": ["input"], "writes": ["output"]},
                {"name": "step-two", "reads": ["output"], "writes": ["final"]},
            ],
            "rules": [
                {"name": "rule-1", "triggers": ["input"], "steps": ["step-one"]},
                {"name": "rule-2", "triggers": ["output"], "steps": ["step-two"]},
            ],
        },
    }


def test_C1_reports_body_diff(tmp_path: Path):
    storage = RegistryStorage(tmp_path / "registry.jsonl")
    registry = ArtifactRegistry(storage=storage)

    base = _base_intent_artifact()
    path_old = _write_artifact(tmp_path, base, "intent-old.yaml")
    _old = _verify_and_register(path_old, registry)

    updated = _base_intent_artifact()
    updated["body"]["goal"] = "Reach every destination"
    path_new = _write_artifact(tmp_path, updated, "intent-new.yaml")
    current = _load_and_verify(path_new)
    report = check_consistency(current, registry)

    assert any(issue.code == ConsistencyCode.C1 for issue in report.issues)
    assert "canonical representation" in report.human_summary
    assert report.machine_readable


def test_C2_warns_without_explanation(tmp_path: Path):
    storage = RegistryStorage(tmp_path / "registry.jsonl")
    registry = ArtifactRegistry(storage=storage)

    intent_path = _write_artifact(tmp_path, _base_intent_artifact(), "intent-base.yaml")
    intent = _verify_and_register(intent_path, registry)
    intent_hash = intent.envelope.body_hash

    derived = _base_plan_artifact()
    derived["envelope"]["artifact_id"] = "tm-plan-0002"
    derived["envelope"]["meta"]["derived_from"] = {"intent_body_hash": intent_hash}
    path_prev = _write_artifact(tmp_path, derived, "derived-old.yaml")
    _verify_and_register(path_prev, registry)

    new_derived = _base_plan_artifact()
    new_derived["envelope"]["artifact_id"] = "tm-plan-0003"
    new_derived["body"]["summary"] = "execute steps v2"
    new_derived["envelope"]["meta"]["derived_from"] = {"intent_body_hash": intent_hash}
    path_new = _write_artifact(tmp_path, new_derived, "derived-new.yaml")
    current = _load_and_verify(path_new)
    report = check_consistency(current, registry)

    assert any(issue.code == ConsistencyCode.C2 for issue in report.issues)

    # explanation suppresses the warning
    new_derived["envelope"]["meta"]["provenance_explanation"] = "tuned writes list"
    path_explained = _write_artifact(tmp_path, new_derived, "derived-explained.yaml")
    current_explained = _load_and_verify(path_explained)
    report_explained = check_consistency(current_explained, registry)
    assert all(issue.code != ConsistencyCode.C2 for issue in report_explained.issues)


def test_C3_detects_invariant_regression(tmp_path: Path):
    storage = RegistryStorage(tmp_path / "registry.jsonl")
    registry = ArtifactRegistry(storage=storage)

    base = _base_intent_artifact()
    base["envelope"]["meta"]["invariant_status"] = {"safe": True, "stable": True}
    path_old = _write_artifact(tmp_path, base, "intent-regression-old.yaml")
    _old = _verify_and_register(path_old, registry)

    new = _base_intent_artifact()
    new["envelope"]["meta"]["invariant_status"] = {"safe": False, "stable": True}
    path_new = _write_artifact(tmp_path, new, "intent-regression-new.yaml")
    current = _load_and_verify(path_new)
    report = check_consistency(current, registry)

    assert any(issue.code == ConsistencyCode.C3 for issue in report.issues)
