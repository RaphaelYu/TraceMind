from pathlib import Path

import pytest
import yaml

from tm.artifacts import ArtifactType, load_yaml_artifact, verify
from tm.artifacts.registry import ArtifactRegistry, RegistryStorage


def _write_artifact(tmp_path: Path, data: dict[str, object], name: str) -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


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


def _create_and_verify(tmp_path: Path, data: dict[str, object], name: str):
    path = _write_artifact(tmp_path, data, name)
    artifact = load_yaml_artifact(path)
    accepted, report = verify(artifact)
    assert accepted is not None
    assert report.success
    return accepted, path


def test_registry_records_and_retrieves_plan(tmp_path: Path):
    artifact, path = _create_and_verify(tmp_path, _base_plan_artifact(), "plan.yaml")
    storage = RegistryStorage(tmp_path / "registry.jsonl")
    registry = ArtifactRegistry(storage=storage)

    entry = registry.add(artifact, path)

    assert registry.get_by_artifact_id(entry.artifact_id) == entry
    assert registry.list_by_type(ArtifactType.PLAN) == [entry]
    assert registry.list_by_body_hash(entry.body_hash) == [entry]
    assert registry.list_all() == [entry]


def test_registry_indexes_intent_id(tmp_path: Path):
    artifact, path = _create_and_verify(tmp_path, _base_intent_artifact(), "intent.yaml")
    storage = RegistryStorage(tmp_path / "registry-intent.jsonl")
    registry = ArtifactRegistry(storage=storage)

    entry = registry.add(artifact, path)

    records = registry.list_by_intent_id("TM-INT-0001")
    assert records == [entry]
    assert entry.intent_id == "TM-INT-0001"


def test_registry_rejects_non_accepted(tmp_path: Path):
    data = _base_plan_artifact()
    path = _write_artifact(tmp_path, data, "candidate.yaml")
    artifact = load_yaml_artifact(path)

    storage = RegistryStorage(tmp_path / "registry-reject.jsonl")
    registry = ArtifactRegistry(storage=storage)

    with pytest.raises(ValueError):
        registry.add(artifact, path)
