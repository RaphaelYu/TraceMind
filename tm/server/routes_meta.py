"""Routes exposing API meta-data for the stable /api/v1 surface."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from tm.server.versioning import get_api_meta


class BuildInfoModel(BaseModel):
    git_commit: str | None
    build_time: str


class MetaResponse(BaseModel):
    api_version: str
    tm_core_version: str
    schemas_supported: list[str]
    build: BuildInfoModel


def create_meta_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/meta", tags=["meta"])

    @router.get("", response_model=MetaResponse)
    def meta() -> dict[str, object]:
        return get_api_meta()

    return router
