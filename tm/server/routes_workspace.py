"""Routes for mounting and inspecting TraceMind workspaces."""

from __future__ import annotations

from typing import Dict, Sequence

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from tm.server.workspace_manager import WorkspaceDescriptor, WorkspaceManager
from tm.workspace.manifest import Workspace

DIRECTORY_KEYS: tuple[str, ...] = (
    "specs",
    "artifacts",
    "reports",
    "prompts",
    "policies",
)


class MountWorkspaceRequest(BaseModel):
    path: str


class SelectWorkspaceRequest(BaseModel):
    workspace_id: str


class WorkspaceInfo(BaseModel):
    workspace_id: str
    name: str
    root: str
    languages: Sequence[str]
    directories: Dict[str, str]
    commit_policy: Dict[str, Sequence[str]]


def _workspace_directories(workspace: Workspace) -> Dict[str, str]:
    return {key: str(getattr(workspace.paths, key)) for key in DIRECTORY_KEYS}


def _workspace_commit_policy(workspace: Workspace) -> Dict[str, Sequence[str]]:
    return {
        "required": list(workspace.manifest.commit_policy.required),
        "optional": list(workspace.manifest.commit_policy.optional),
    }


def _describe(
    workspace: WorkspaceDescriptor, directories: Dict[str, str], commit_policy: Dict[str, Sequence[str]]
) -> WorkspaceInfo:
    return WorkspaceInfo(
        workspace_id=workspace.workspace_id,
        name=workspace.name,
        root=str(workspace.root),
        languages=list(workspace.languages),
        directories=directories,
        commit_policy=commit_policy,
    )


def create_workspace_router(manager: WorkspaceManager) -> APIRouter:
    router = APIRouter(prefix="/api/v1/workspaces", tags=["workspace"])

    @router.post("/mount", response_model=WorkspaceInfo)
    def mount_workspace(payload: MountWorkspaceRequest) -> WorkspaceInfo:
        try:
            workspace = manager.mount(payload.path)
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        descriptor = WorkspaceDescriptor.from_workspace(workspace)
        directories = _workspace_directories(workspace)
        commit_policy = _workspace_commit_policy(workspace)
        return _describe(descriptor, directories, commit_policy)

    @router.get("", response_model=Sequence[WorkspaceInfo])
    def list_workspaces() -> Sequence[WorkspaceInfo]:
        output: list[WorkspaceInfo] = []
        for workspace in manager.list():
            descriptor = WorkspaceDescriptor.from_workspace(workspace)
            directories = _workspace_directories(workspace)
            commit_policy = _workspace_commit_policy(workspace)
            output.append(_describe(descriptor, directories, commit_policy))
        return output

    @router.post("/select", response_model=WorkspaceInfo)
    def select_workspace(payload: SelectWorkspaceRequest) -> WorkspaceInfo:
        try:
            workspace = manager.select(payload.workspace_id)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        descriptor = WorkspaceDescriptor.from_workspace(workspace)
        directories = _workspace_directories(workspace)
        commit_policy = _workspace_commit_policy(workspace)
        return _describe(descriptor, directories, commit_policy)

    @router.get("/current", response_model=WorkspaceInfo | None)
    def get_current_workspace() -> WorkspaceInfo | None:
        workspace = manager.current()
        if workspace is None:
            return None
        descriptor = WorkspaceDescriptor.from_workspace(workspace)
        directories = _workspace_directories(workspace)
        commit_policy = _workspace_commit_policy(workspace)
        return _describe(descriptor, directories, commit_policy)

    return router
