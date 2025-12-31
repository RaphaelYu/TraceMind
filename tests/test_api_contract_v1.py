"""Contract sanity checks for the stable `/api/v1` surface."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import pytest
from fastapi import HTTPException

from tm.server.config import ServerConfig
from tm.server.routes_artifacts import ArtifactCreateRequest, create_artifact_router
from tm.server.routes_controller import (
    CycleRunRequest,
    create_controller_router,
    create_controller_v1_router,
)
from tm.server.routes_llm import create_llm_router
from tm.server.routes_meta import create_meta_router
from tm.server.routes_workspace import MountWorkspaceRequest, create_workspace_router
from tm.server.workspace_manager import WorkspaceManager
from tm.workspace.init import initialize_workspace


def _get_endpoint(router, name: str):
    for route in router.routes:
        if route.name == name:
            return route.endpoint
    raise KeyError(name)


@pytest.fixture
def workspace_context(tmp_path: Path) -> dict[str, object]:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir(parents=True)
    initialize_workspace(workspace_root, name="contract-test", append_gitignore=False)
    manager = WorkspaceManager()
    workspace = manager.mount(workspace_root)
    config = ServerConfig(base_dir=tmp_path / "server")

    routers = {
        "workspace": create_workspace_router(manager),
        "artifact": create_artifact_router(config, manager),
        "controller": create_controller_router(config, manager),
        "controller_v1": create_controller_v1_router(config, manager),
        "llm": create_llm_router(manager),
        "meta": create_meta_router(),
    }
    return {
        "workspace_manager": manager,
        "workspace_id": workspace.manifest.workspace_id,
        "root": workspace_root,
        **routers,
    }


def test_meta_contract(workspace_context: dict[str, object]) -> None:
    meta_router = workspace_context["meta"]
    meta_route = next((route for route in meta_router.routes if route.name == "meta"), None)
    assert meta_route is not None
    result = meta_route.endpoint()
    assert result["api_version"] == "v1"
    assert isinstance(result["tm_core_version"], str)
    assert isinstance(result["schemas_supported"], Sequence)
    build = result["build"]
    assert isinstance(build["git_commit"], str) or build["git_commit"] is None
    assert isinstance(build["build_time"], str)


def test_workspace_contract(workspace_context: dict[str, object]) -> None:
    workspace_router = workspace_context["workspace"]
    root = workspace_context["root"]
    mount_endpoint = _get_endpoint(workspace_router, "mount_workspace")
    list_endpoint = _get_endpoint(workspace_router, "list_workspaces")
    current_endpoint = _get_endpoint(workspace_router, "get_current_workspace")
    info = mount_endpoint(MountWorkspaceRequest(path=str(root)))
    assert hasattr(info, "workspace_id")
    listed = list_endpoint()
    assert any(entry.workspace_id == info.workspace_id for entry in listed)
    current = current_endpoint()
    assert current is not None and current.workspace_id == info.workspace_id


def _intent_payload(artifact_id: str) -> dict[str, object]:
    return {
        "intent_id": artifact_id,
        "title": "Contract intent",
        "context": "Testing context",
        "goal": "Contract validation",
        "non_goals": [],
        "actors": ["system"],
        "inputs": ["state:contract"],
        "outputs": ["artifact:contract"],
        "constraints": [],
        "success_metrics": [],
        "risks": [],
        "assumptions": [],
        "trace_links": {"parent_intent": None, "related_intents": []},
    }


def test_artifacts_contract(workspace_context: dict[str, object]) -> None:
    artifact_router = workspace_context["artifact"]
    workspace_id = workspace_context["workspace_id"]
    artifact_id = "tm-intent/contracts/roundtrip"
    payload = ArtifactCreateRequest(artifact_type="intent", body=_intent_payload(artifact_id))
    create_endpoint = _get_endpoint(artifact_router, "create_artifact")
    list_endpoint = _get_endpoint(artifact_router, "list_artifacts")
    detail_endpoint = _get_endpoint(artifact_router, "get_artifact")
    update_endpoint = _get_endpoint(artifact_router, "update_artifact")
    created = create_endpoint(payload, workspace_id)
    assert created.entry.artifact_id == artifact_id
    assert created.entry.schema_version
    listed = list_endpoint(artifact_type=None, workspace_id=workspace_id)
    assert any(entry.artifact_id == artifact_id for entry in listed)
    detail = detail_endpoint(artifact_id, workspace_id)
    assert detail.entry.artifact_id == artifact_id
    updated_body = _intent_payload(artifact_id)
    updated_body["goal"] = "Updated goal"
    updated = update_endpoint(
        artifact_id, ArtifactCreateRequest(artifact_type="intent", body=updated_body), workspace_id
    )
    assert updated.document.body["goal"] == "Updated goal"
    with pytest.raises(ValueError):
        update_endpoint(
            artifact_id, ArtifactCreateRequest(artifact_type="intent", body={"intent_id": artifact_id}), workspace_id
        )


def test_llm_configs_contract(workspace_context: dict[str, object]) -> None:
    llm_router = workspace_context["llm"]
    workspace_id = workspace_context["workspace_id"]
    templates_endpoint = _get_endpoint(llm_router, "list_prompt_templates")
    configs_endpoint = _get_endpoint(llm_router, "list_configs")
    create_endpoint = _get_endpoint(llm_router, "create_config")
    templates = templates_endpoint()
    if not templates:
        pytest.skip("no prompt templates available for contract")
    version = templates[0].version
    created = create_endpoint(
        payload={
            "model": "contract-model",
            "prompt_template_version": version,
            "prompt_version": None,
            "model_id": None,
            "model_version": None,
        },
        workspace_id=workspace_id,
    )
    assert created.config_id
    listed = configs_endpoint(workspace_id=workspace_id)
    assert any(entry.config_id == created.config_id for entry in listed)


def test_controller_cycle_and_runs_contract(workspace_context: dict[str, object]) -> None:
    controller_router = workspace_context["controller_v1"]
    workspace_id = workspace_context["workspace_id"]
    with pytest.raises(HTTPException) as cycle_exc:
        controller_router.run_cycle(
            CycleRunRequest(bundle_artifact_id="missing", mode="live", workspace_id=workspace_id)
        )
    assert cycle_exc.value.status_code == 404
    with pytest.raises(HTTPException) as report_exc:
        controller_router.get_report("missing-run", workspace_id)
    assert report_exc.value.status_code == 404
