from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from tm.artifacts import Artifact
from tm.artifacts.registry import ArtifactRegistry, RegistryStorage
from tm.controllers.cycle import ControllerCycle, ControllerCycleError, write_gap_and_backlog
from tm.utils.yaml import import_yaml

from tests.test_controller_demo_bundle_v0 import _build_controller_bundle

yaml = import_yaml()


def _artifact_document(artifact: Artifact) -> dict[str, object]:
    envelope = asdict(artifact.envelope)
    envelope["status"] = artifact.envelope.status.value
    envelope["artifact_type"] = artifact.envelope.artifact_type.value
    if artifact.envelope.signature is None:
        envelope.pop("signature", None)
    return {"envelope": envelope, "body": dict(artifact.body_raw)}


def _write_bundle(path: Path, artifact: Artifact) -> None:
    doc = _artifact_document(artifact)
    path.parent.mkdir(parents=True, exist_ok=True)
    if yaml is not None:
        with path.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(doc, handle, sort_keys=True, allow_unicode=True)
        return
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")


def _bundle_artifact(path: Path, policy_allow: list[str] | None) -> None:
    bundle = _build_controller_bundle(policy_allow)
    _write_bundle(path, bundle)


def _create_registry(tmp_path: Path) -> ArtifactRegistry:
    storage = RegistryStorage(tmp_path / "registry.jsonl")
    return ArtifactRegistry(storage)


def test_controller_cycle_records_artifacts(tmp_path: Path) -> None:
    bundle_path = tmp_path / "controller_bundle.yaml"
    _bundle_artifact(bundle_path, ["state:env.snapshot", "artifact:proposed.plan", "resource:inventory:update"])
    artifacts_dir = tmp_path / "controller_artifacts"
    registry = _create_registry(tmp_path)
    runner = ControllerCycle(
        bundle_path=bundle_path,
        report_path=tmp_path / "cycle_report.yaml",
        artifact_output_dir=artifacts_dir,
        dry_run=True,
        record_path=tmp_path / "decide_records.json",
        registry=registry,
    )
    result = runner.run()
    assert artifacts_dir.joinpath("env_snapshot.yaml").exists()
    assert artifacts_dir.joinpath("proposed_change_plan.yaml").exists()
    assert artifacts_dir.joinpath("execution_report.yaml").exists()
    assert result.bundle_artifact_id
    assert result.policy_decisions == []


def test_controller_cycle_emits_gap_backlog_on_policy_denial(tmp_path: Path) -> None:
    bundle_path = tmp_path / "controller_bundle_denied.yaml"
    _bundle_artifact(bundle_path, None)
    runner = ControllerCycle(
        bundle_path=bundle_path,
        report_path=tmp_path / "cycle_report.yaml",
        artifact_output_dir=tmp_path / "controller_artifacts",
        dry_run=True,
        record_path=tmp_path / "decide_records.json",
        registry=_create_registry(tmp_path),
    )
    with pytest.raises(ControllerCycleError) as excinfo:
        runner.run()
    errors = excinfo.value.errors
    assert any("policy guard denied" in err for err in errors)
    gap_path, backlog_path = write_gap_and_backlog(
        tmp_path / "cycle_report.yaml", runner.bundle_artifact_id or bundle_path.name, errors
    )
    assert gap_path.exists()
    assert backlog_path.exists()
