"""Regression around controller routes that touch artifacts."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from tm.artifacts.registry import ArtifactRegistry, RegistryStorage
from tm.artifacts import Artifact
from tm.server.config import ServerConfig
from tm.server.routes_controller import create_controller_router
from tm.server.workspace_manager import WorkspaceManager
from tm.utils.yaml import import_yaml

from tests.test_controller_demo_bundle_v0 import _build_controller_bundle

yaml = import_yaml()


def _write_document(path: Path, document: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if yaml is not None:
        with path.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(document, handle, sort_keys=True)
        return
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")


def _artifact_document(artifact: Artifact) -> dict[str, object]:
    envelope = asdict(artifact.envelope)
    envelope["status"] = artifact.envelope.status.value
    envelope["artifact_type"] = artifact.envelope.artifact_type.value
    if artifact.envelope.signature is None:
        envelope.pop("signature", None)
    return {"envelope": envelope, "body": dict(artifact.body_raw)}


def test_artifact_detail_accepts_slashes(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir(parents=True)
    manifest = {"workspace_id": "tm-workspace:///controller", "name": "controller-test"}
    _write_document(workspace_root / "tracemind.workspace.yaml", manifest)

    manager = WorkspaceManager()
    workspace = manager.mount(workspace_root)
    workspace.paths.artifacts.mkdir(parents=True, exist_ok=True)

    bundle = _build_controller_bundle(
        [
            "state:env.snapshot",
            "artifact:proposed.plan",
            "resource:inventory:update",
        ]
    )
    artifact_path = workspace.paths.artifacts / "controller_bundle.yaml"
    _write_document(artifact_path, _artifact_document(bundle))

    storage = RegistryStorage(workspace.paths.registry)
    ArtifactRegistry(storage).add(bundle, artifact_path)

    router = create_controller_router(ServerConfig(base_dir=tmp_path / "server"), manager)
    detail = router.get_artifact(bundle.envelope.artifact_id, workspace.manifest.workspace_id)
    assert detail["entry"]["artifact_id"] == bundle.envelope.artifact_id
    assert detail["document"]["envelope"]["artifact_id"] == bundle.envelope.artifact_id
