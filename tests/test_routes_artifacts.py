"""Tests for the artifact CRUD routes exposed by tm-server."""

from __future__ import annotations

from pathlib import Path

from tm.server.config import ServerConfig
from tm.server.routes_artifacts import ArtifactCreateRequest, create_artifact_router
from tm.server.workspace_manager import WorkspaceManager
from tm.utils.yaml import import_yaml

yaml = import_yaml()


def _write_manifest(path: Path, data: dict[str, object]) -> None:
    if yaml is None:
        raise RuntimeError("PyYAML is required to write workspace manifests")
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=True)


def test_artifact_roundtrip_create_get_update(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir(parents=True)
    manifest = {"workspace_id": "tm-workspace://artifacts", "name": "artifact-test"}
    _write_manifest(workspace_root / "tracemind.workspace.yaml", manifest)

    manager = WorkspaceManager()
    workspace = manager.mount(workspace_root)
    router = create_artifact_router(ServerConfig(base_dir=tmp_path / "server"), manager)

    endpoints = {route.name: route.endpoint for route in router.routes}
    create_endpoint = endpoints["create_artifact"]
    get_endpoint = endpoints["get_artifact"]
    update_endpoint = endpoints["update_artifact"]

    artifact_id = "tm-intent/artifacts/test"
    initial_body = {
        "intent_id": artifact_id,
        "title": "Notification intent",
        "context": "Test context",
        "goal": "Notify within 5s",
        "non_goals": [],
        "actors": ["system"],
        "inputs": ["incident.created"],
        "outputs": ["incident.notification"],
        "constraints": [],
        "success_metrics": [],
        "risks": [],
        "assumptions": [],
        "trace_links": {"parent_intent": None, "related_intents": []},
    }

    request = ArtifactCreateRequest(artifact_type="intent", body=initial_body)
    created = create_endpoint(request, workspace.manifest.workspace_id)
    assert created.entry.artifact_id == artifact_id
    assert created.document.body["goal"] == "Notify within 5s"

    fetched = get_endpoint(artifact_id, workspace.manifest.workspace_id)
    assert fetched.entry.artifact_id == artifact_id
    assert fetched.document.body["goal"] == initial_body["goal"]

    updated_body = dict(initial_body)
    updated_body["goal"] = "Notify within 3s"
    update_request = ArtifactCreateRequest(artifact_type="intent", body=updated_body)
    updated = update_endpoint(artifact_id, update_request, workspace.manifest.workspace_id)
    assert updated.document.body["goal"] == "Notify within 3s"

    refreshed = get_endpoint(artifact_id, workspace.manifest.workspace_id)
    assert refreshed.document.body["goal"] == "Notify within 3s"
