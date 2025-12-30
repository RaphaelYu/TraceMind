"""Regression tests for the TM server controller helper logic."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from tm.artifacts import Artifact
from tm.artifacts.registry import ArtifactRegistry, RegistryStorage
from tm.server.config import ServerConfig
from tm.server.routes_controller import (
    ArtifactDiffRequest,
    CycleRunRequest,
    create_controller_router,
)
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


def _prepare_registry(tmp_path: Path) -> tuple[ServerConfig, ArtifactRegistry]:
    config = ServerConfig(
        base_dir=tmp_path / "server",
        registry_path=tmp_path / "registry.jsonl",
        record_path=tmp_path / "decide_records.json",
    )
    storage = RegistryStorage(config.registry_path)
    return config, ArtifactRegistry(storage)


def test_controller_server_cycle_flow(tmp_path: Path) -> None:
    config, registry = _prepare_registry(tmp_path)
    bundle = _build_controller_bundle(
        [
            "state:env.snapshot",
            "artifact:proposed.plan",
            "resource:inventory:update",
        ]
    )
    bundle_path = (tmp_path / "bundle.yaml").resolve()
    _write_bundle(bundle_path, bundle)
    registry.add(bundle, bundle_path)
    router = create_controller_router(config)

    bundles = router.list_bundles()
    assert any(entry["artifact_id"] == bundle.envelope.artifact_id for entry in bundles)

    response = router.run_cycle(CycleRunRequest(bundle_artifact_id=bundle.envelope.artifact_id, mode="live"))
    assert response.success
    assert response.report["bundle_artifact_id"] == bundle.envelope.artifact_id
    run_id = response.run_id

    reports = router.list_reports()
    assert run_id in {entry["run_id"] for entry in reports}

    detail = router.get_report(run_id)
    assert detail["bundle_artifact_id"] == bundle.envelope.artifact_id

    artifacts = router.list_artifacts(artifact_type="agent_bundle")
    assert any(entry["artifact_id"] == bundle.envelope.artifact_id for entry in artifacts)

    diff = router.diff_artifacts(
        ArtifactDiffRequest(base_id=bundle.envelope.artifact_id, compare_id=bundle.envelope.artifact_id)
    )
    assert diff["diff"] == []
