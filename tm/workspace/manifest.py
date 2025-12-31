"""Workspace manifest loader and resolver."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from tm.utils.yaml import import_yaml

from .paths import WorkspacePaths

yaml = import_yaml()


DEFAULT_DIRECTORIES: Mapping[str, str] = {
    "specs": "specs",
    "artifacts": ".tracemind",
    "reports": "reports",
    "prompts": "prompts",
    "policies": "policies",
}


@dataclass(frozen=True)
class CommitPolicy:
    required: tuple[str, ...] = field(default_factory=tuple)
    optional: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Sequence[str]] | None) -> "CommitPolicy":
        if not data:
            return cls()
        required = tuple(str(item) for item in data.get("required") or [])
        optional = tuple(str(item) for item in data.get("optional") or [])
        return cls(required=required, optional=optional)


@dataclass(frozen=True)
class WorkspaceManifest:
    workspace_id: str
    name: str
    root: Path
    directories: Mapping[str, str]
    commit_policy: CommitPolicy
    languages: tuple[str, ...]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any], manifest_path: Path) -> "WorkspaceManifest":
        base = manifest_path.parent
        workspace_id = str(data.get("workspace_id", ""))
        name = str(data.get("name", ""))
        if not workspace_id or not name:
            raise ValueError("manifest must declare workspace_id and name")
        root = Path(str(data.get("root", ".")))
        resolved_root = (base / root).resolve()
        directories: dict[str, str] = {}
        raw_dirs = data.get("directories") or {}
        if not isinstance(raw_dirs, Mapping):
            raise TypeError("directories must be a mapping")
        for key, value in DEFAULT_DIRECTORIES.items():
            directories[key] = str(raw_dirs.get(key, value))
        commit_policy = CommitPolicy.from_mapping(data.get("commit_policy"))
        langs = data.get("languages") or []
        if isinstance(langs, Sequence) and not isinstance(langs, (str, bytes, bytearray)):
            languages = tuple(str(item) for item in langs if item is not None)
        else:
            languages = ()
        return cls(
            workspace_id=workspace_id,
            name=name,
            root=resolved_root,
            directories=directories,
            commit_policy=commit_policy,
            languages=languages,
        )


@dataclass(frozen=True)
class Workspace:
    manifest: WorkspaceManifest
    paths: WorkspacePaths
    manifest_path: Path


def _resolve_directories(root: Path, overrides: Mapping[str, str]) -> WorkspacePaths:
    specs = root / overrides.get("specs", DEFAULT_DIRECTORIES["specs"])
    artifacts = root / overrides.get("artifacts", DEFAULT_DIRECTORIES["artifacts"])
    reports = root / overrides.get("reports", DEFAULT_DIRECTORIES["reports"])
    prompts = root / overrides.get("prompts", DEFAULT_DIRECTORIES["prompts"])
    policies = root / overrides.get("policies", DEFAULT_DIRECTORIES["policies"])
    return WorkspacePaths(
        root=root,
        specs=specs.resolve(),
        artifacts=artifacts.resolve(),
        reports=reports.resolve(),
        prompts=prompts.resolve(),
        policies=policies.resolve(),
    )


def load_workspace(directory: Path | str) -> Workspace:
    base = Path(directory)
    manifest_path = base / "tracemind.workspace.yaml"
    if not manifest_path.exists():
        raise FileNotFoundError(f"workspace manifest not found: {manifest_path}")
    if yaml is None:
        raise RuntimeError("PyYAML is required to load workspace manifests")
    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("workspace manifest must be a mapping")
    manifest = WorkspaceManifest.from_mapping(raw, manifest_path)
    paths = _resolve_directories(manifest.root, manifest.directories)
    return Workspace(manifest=manifest, paths=paths, manifest_path=manifest_path)
