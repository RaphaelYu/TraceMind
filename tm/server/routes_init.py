"""Routes that bootstrap a TraceMind workspace on disk."""

from __future__ import annotations

from typing import Dict, Mapping, Sequence

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from tm.workspace.init import initialize_workspace


class WorkspaceInitRequest(BaseModel):
    path: str
    name: str
    workspace_id: str | None = None
    languages: Sequence[str] | None = None
    directories: Mapping[str, str] | None = None
    commit_policy: Mapping[str, Sequence[str]] | None = None
    append_gitignore: bool = False


class WorkspaceInitResponse(BaseModel):
    workspace_id: str
    name: str
    manifest_path: str
    directories: Dict[str, str]
    sample_controller_bundle: str
    sample_intent: str
    gitignore_snippet: str
    gitignore_path: str | None


def create_init_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/workspaces/init", tags=["workspace"])

    @router.post("", response_model=WorkspaceInitResponse)
    def init_workspace_route(payload: WorkspaceInitRequest) -> WorkspaceInitResponse:
        try:
            result = initialize_workspace(
                payload.path,
                name=payload.name,
                workspace_id=payload.workspace_id,
                languages=payload.languages,
                directories=payload.directories,
                commit_policy=payload.commit_policy,
                append_gitignore=payload.append_gitignore,
            )
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return WorkspaceInitResponse(
            workspace_id=result.workspace_id,
            name=result.name,
            manifest_path=str(result.manifest_path),
            directories={key: str(path) for key, path in result.directories.items()},
            sample_controller_bundle=str(result.sample_controller_bundle),
            sample_intent=str(result.sample_intent),
            gitignore_snippet=result.gitignore_snippet,
            gitignore_path=str(result.gitignore_path) if result.gitignore_path else None,
        )

    return router
