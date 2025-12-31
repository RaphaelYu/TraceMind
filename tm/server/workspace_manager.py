"""Tracks mounted TraceMind workspaces for the HTTP API."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Sequence

from tm.workspace import Workspace, load_workspace


@dataclass(frozen=True)
class WorkspaceDescriptor:
    workspace_id: str
    name: str
    root: Path
    languages: tuple[str, ...]

    @classmethod
    def from_workspace(cls, workspace: Workspace) -> "WorkspaceDescriptor":
        return cls(
            workspace_id=workspace.manifest.workspace_id,
            name=workspace.manifest.name,
            root=workspace.manifest.root,
            languages=workspace.manifest.languages,
        )


class WorkspaceManager:
    def __init__(self) -> None:
        self._workspaces: Dict[str, Workspace] = {}
        self._current: str | None = None

    def mount(self, path: str | Path) -> Workspace:
        workspace = load_workspace(path)
        self._workspaces[workspace.manifest.workspace_id] = workspace
        if self._current is None:
            self._current = workspace.manifest.workspace_id
        return workspace

    def list(self) -> Sequence[Workspace]:
        return list(self._workspaces.values())

    def get(self, workspace_id: str | None = None) -> Workspace:
        target = workspace_id or self._current
        if target is None:
            raise KeyError("no workspace selected")
        try:
            return self._workspaces[target]
        except KeyError as exc:
            raise KeyError(f"workspace '{target}' not mounted") from exc

    def select(self, workspace_id: str) -> Workspace:
        workspace = self.get(workspace_id)
        self._current = workspace_id
        return workspace

    def current(self) -> Workspace | None:
        if self._current is None:
            return None
        return self._workspaces.get(self._current)
