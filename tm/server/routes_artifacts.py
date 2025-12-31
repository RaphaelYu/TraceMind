"""Workspace-aware routes for creating, listing, and updating artifacts."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from tm.artifacts import verify
from tm.artifacts.models import (
    AgentBundleBody,
    Artifact,
    ArtifactEnvelope,
    ArtifactType,
    ArtifactStatus,
    IntentBody,
)
from tm.artifacts.registry import ArtifactRegistry, RegistryEntry
from tm.artifacts.storage import RegistryStorage
from tm.server.config import ServerConfig
from tm.server.workspace_manager import WorkspaceManager
from tm.utils.yaml import import_yaml
from tm.workspace.manifest import Workspace

yaml = import_yaml()


class ArtifactEntryResponse(BaseModel):
    artifact_id: str
    artifact_type: str
    body_hash: str
    path: str
    meta: Dict[str, Any]
    version: str
    schema_version: str
    created_at: str
    status: str
    intent_id: str | None = None


class ArtifactDocument(BaseModel):
    envelope: Dict[str, Any]
    body: Dict[str, Any]


class ArtifactDetailResponse(BaseModel):
    entry: ArtifactEntryResponse
    document: ArtifactDocument


class ArtifactCreateRequest(BaseModel):
    artifact_type: str
    body: Mapping[str, Any]


def _resolve_workspace(workspace_manager: WorkspaceManager, workspace_id: str | None) -> Workspace:
    try:
        return workspace_manager.get(workspace_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


def _artifact_registry(workspace: Workspace) -> ArtifactRegistry:
    workspace.paths.artifacts.mkdir(parents=True, exist_ok=True)
    workspace.paths.registry.parent.mkdir(parents=True, exist_ok=True)
    return ArtifactRegistry(RegistryStorage(workspace.paths.registry))


def _format_entry(entry: RegistryEntry) -> ArtifactEntryResponse:
    data = entry.to_dict()
    data["schema_version"] = entry.version
    return ArtifactEntryResponse(**data)


def _read_artifact_document(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if not isinstance(data, Mapping):
        raise ValueError(f"expected document mapping at {path}")
    return dict(data)


def _write_document(path: Path, document: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if yaml is not None:
        with path.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(document, handle, sort_keys=True, allow_unicode=True)
        return
    path.write_text(json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8")


def _artifact_document(artifact: Artifact) -> dict[str, Any]:
    envelope = asdict(artifact.envelope)
    envelope["status"] = artifact.envelope.status.value
    envelope["artifact_type"] = artifact.envelope.artifact_type.value
    if artifact.envelope.signature is None:
        envelope.pop("signature", None)
    return {"envelope": envelope, "body": dict(artifact.body_raw)}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize_artifact_id(artifact_id: str) -> str:
    candidate = artifact_id.strip()
    if not candidate:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="artifact_id must not be empty")
    if candidate.startswith("/") or candidate.endswith("..") or "/.." in candidate:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="artifact_id contains invalid path segments"
        )
    return candidate


def _artifact_storage_path(workspace: Workspace, artifact_type: ArtifactType, artifact_id: str) -> Path:
    safe_id = artifact_id.replace("\\", "/").lstrip("/")
    parts = [part for part in safe_id.split("/") if part]
    if not parts:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="artifact_id contains invalid characters")
    target = workspace.paths.specs / artifact_type.value
    target_path = target.joinpath(*parts).with_suffix(".yaml")
    try:
        resolved = target_path.resolve()
    except RuntimeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid artifact_id path")
    try:
        resolved.relative_to(workspace.paths.specs)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="artifact_id resolves outside workspace specs",
        )
    return target_path


def _build_entry_response(entry: RegistryEntry, document: Mapping[str, Any]) -> ArtifactDetailResponse:
    return ArtifactDetailResponse(entry=_format_entry(entry), document=ArtifactDocument(**document))


def _artifact_body_class(artifact_type: ArtifactType):
    if artifact_type == ArtifactType.INTENT:
        return IntentBody
    if artifact_type == ArtifactType.AGENT_BUNDLE:
        return AgentBundleBody
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST, detail=f"artifact type '{artifact_type.value}' not supported"
    )


def _build_candidate_artifact(
    *,
    artifact_type: ArtifactType,
    artifact_id: str,
    body_payload: Mapping[str, Any],
    workspace: Workspace,
) -> Artifact:
    body_dict = dict(body_payload)
    body_cls = _artifact_body_class(artifact_type)
    body_instance = body_cls.from_mapping(body_dict)
    envelope = ArtifactEnvelope(
        artifact_id=artifact_id,
        status=ArtifactStatus.CANDIDATE,
        artifact_type=artifact_type,
        version="v0",
        created_by="controller.studio",
        created_at=_iso_now(),
        body_hash="",
        envelope_hash="",
        meta={"phase": "artifact-edit", "workspace_id": workspace.manifest.workspace_id},
    )
    return Artifact(envelope=envelope, body=body_instance, body_raw=dict(body_dict))


def _derive_artifact_id(artifact_type: ArtifactType, body_payload: Mapping[str, Any]) -> str:
    if artifact_type == ArtifactType.INTENT:
        value = body_payload.get("intent_id")
    elif artifact_type == ArtifactType.AGENT_BUNDLE:
        value = body_payload.get("bundle_id")
    else:
        value = body_payload.get("artifact_id") or body_payload.get("id")
    if value is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{artifact_type.value} body must include identifier",
        )
    return _sanitize_artifact_id(str(value))


def _verify_candidate(artifact: Artifact) -> Artifact:
    accepted, report = verify(artifact)
    if accepted is None or not report.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"errors": report.errors},
        )
    return accepted


def _rewrite_registry_entries(workspace: Workspace, entries: Iterable[RegistryEntry]) -> None:
    workspace.paths.registry.parent.mkdir(parents=True, exist_ok=True)
    with workspace.paths.registry.open("w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry.to_dict(), ensure_ascii=False))
            handle.write("\n")


def _load_document_from_entry(entry: RegistryEntry, workspace: Workspace) -> Mapping[str, Any]:
    candidate_path = Path(entry.path)
    if not candidate_path.exists():
        raise FileNotFoundError(entry.path)
    return _read_artifact_document(candidate_path)


def create_artifact_router(config: ServerConfig, workspace_manager: WorkspaceManager) -> APIRouter:
    router = APIRouter(prefix="/api/v1/artifacts", tags=["artifacts"])

    @router.get("", response_model=list[ArtifactEntryResponse])
    def list_artifacts(
        artifact_type: str | None = None,
        workspace_id: str | None = Query(None, description="Workspace to scope artifacts"),
    ) -> List[ArtifactEntryResponse]:
        workspace = _resolve_workspace(workspace_manager, workspace_id)
        registry = _artifact_registry(workspace)
        entries = registry.list_all()
        if artifact_type:
            try:
                target_type = ArtifactType(artifact_type)
            except ValueError as exc:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
            entries = [entry for entry in entries if entry.artifact_type == target_type]
        return [_format_entry(entry) for entry in entries]

    @router.get("/{artifact_id:path}", response_model=ArtifactDetailResponse)
    def get_artifact(
        artifact_id: str, workspace_id: str | None = Query(None, description="Workspace to scope artifacts")
    ) -> ArtifactDetailResponse:
        artifact_id = _sanitize_artifact_id(artifact_id)
        workspace = _resolve_workspace(workspace_manager, workspace_id)
        registry = _artifact_registry(workspace)
        entry = registry.get_by_artifact_id(artifact_id)
        if entry is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="artifact not found")
        document = _load_document_from_entry(entry, workspace)
        return _build_entry_response(entry, document)

    @router.post("", response_model=ArtifactDetailResponse)
    def create_artifact(
        payload: ArtifactCreateRequest,
        workspace_id: str | None = Query(None, description="Workspace to persist the artifact"),
    ) -> ArtifactDetailResponse:
        workspace = _resolve_workspace(workspace_manager, workspace_id)
        try:
            artifact_type = ArtifactType(payload.artifact_type)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        artifact_id = _derive_artifact_id(artifact_type, payload.body)
        registry = _artifact_registry(workspace)
        if registry.get_by_artifact_id(artifact_id) is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="artifact already exists")
        artifact = _build_candidate_artifact(
            artifact_type=artifact_type, artifact_id=artifact_id, body_payload=payload.body, workspace=workspace
        )
        accepted = _verify_candidate(artifact)
        target_path = _artifact_storage_path(workspace, artifact_type, artifact_id)
        document = _artifact_document(accepted)
        _write_document(target_path, document)
        entry = registry.add(accepted, target_path)
        return _build_entry_response(entry, document)

    @router.put("/{artifact_id:path}", response_model=ArtifactDetailResponse)
    def update_artifact(
        artifact_id: str,
        payload: ArtifactCreateRequest,
        workspace_id: str | None = Query(None, description="Workspace to persist the artifact"),
    ) -> ArtifactDetailResponse:
        artifact_id = _sanitize_artifact_id(artifact_id)
        workspace = _resolve_workspace(workspace_manager, workspace_id)
        registry = _artifact_registry(workspace)
        entry = registry.get_by_artifact_id(artifact_id)
        if entry is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="artifact not registered")
        try:
            artifact_type = ArtifactType(payload.artifact_type)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        if entry.artifact_type != artifact_type:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="artifact_type mismatch")
        candidate = _build_candidate_artifact(
            artifact_type=artifact_type, artifact_id=artifact_id, body_payload=payload.body, workspace=workspace
        )
        accepted = _verify_candidate(candidate)
        target_path = _artifact_storage_path(workspace, artifact_type, artifact_id)
        document = _artifact_document(accepted)
        _write_document(target_path, document)
        entries = [existing for existing in registry.list_all() if existing.artifact_id != artifact_id]
        new_entry = RegistryEntry.from_artifact(accepted, target_path)
        entries.append(new_entry)
        _rewrite_registry_entries(workspace, entries)
        return _build_entry_response(new_entry, document)

    return router
