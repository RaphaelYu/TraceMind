from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from tm.runtime.reliability import cancel_run, get_run_entry, list_runs
from tm.server.workspace_manager import WorkspaceManager


class RunStatusResponse(BaseModel):
    run_id: str
    workspace_id: str | None
    bundle_artifact_id: str | None
    status: str
    current_step: str | None
    attempt: int
    retry_count: int
    timeout_step: str | None
    timeout_seconds: float | None
    timeout_reason: str | None
    canceled: bool
    started_at: str
    ended_at: str | None
    errors: List[str]
    last_error: str | None


def _resolve_workspace(workspace_manager: WorkspaceManager, workspace_id: str | None):
    try:
        return workspace_manager.get(workspace_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


def create_runs_router(config, workspace_manager: WorkspaceManager) -> APIRouter:
    router = APIRouter(prefix="/api/v1/runs", tags=["runs"])

    @router.get("/", response_model=List[RunStatusResponse])
    def list_run_statuses(workspace_id: str | None = Query(None, description="Workspace owning the run")) -> List[dict]:
        if workspace_id is not None:
            _resolve_workspace(workspace_manager, workspace_id)
        states = list_runs(workspace_id)
        return [RunStatusResponse(**state.to_dict()).dict() for state in states]

    @router.get("/{run_id}")
    def get_run_status(
        run_id: str, workspace_id: str | None = Query(None, description="Workspace owning the run")
    ) -> dict:
        if workspace_id is not None:
            _resolve_workspace(workspace_manager, workspace_id)
        entry = get_run_entry(run_id)
        if entry is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
        if workspace_id is not None and entry.workspace_id != workspace_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
        return RunStatusResponse(**entry.controller.state.to_dict()).dict()

    @router.post("/{run_id}/cancel")
    def cancel_run_request(
        run_id: str, workspace_id: str | None = Query(None, description="Workspace owning the run")
    ) -> dict:
        if workspace_id is not None:
            _resolve_workspace(workspace_manager, workspace_id)
        state = cancel_run(run_id)
        if state is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
        if workspace_id is not None and state.workspace_id != workspace_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
        return RunStatusResponse(**state.to_dict()).dict()

    return router
