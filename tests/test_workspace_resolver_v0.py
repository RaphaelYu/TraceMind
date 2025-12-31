"""Tests for workspace manifest loading and path resolution."""

from __future__ import annotations

from pathlib import Path

from tm.workspace import load_workspace
from tm.utils.yaml import import_yaml

yaml = import_yaml()


def _write_manifest(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if yaml is not None:
        with path.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(payload, handle, sort_keys=True)
        return
    path.write_text("{}", encoding="utf-8")


def test_load_workspace_defaults(tmp_path: Path) -> None:
    manifest = {
        "workspace_id": "trace-mind:///default",
        "name": "Default",
    }
    manifest_path = tmp_path / "tracemind.workspace.yaml"
    _write_manifest(manifest_path, manifest)
    workspace = load_workspace(tmp_path)
    assert workspace.manifest.workspace_id == manifest["workspace_id"]
    assert workspace.paths.specs == (tmp_path / "specs").resolve()
    assert workspace.paths.artifacts == (tmp_path / ".tracemind").resolve()
    assert workspace.paths.intents.name == "intents"
    assert workspace.paths.accepted == (workspace.paths.artifacts / "accepted").resolve()
    assert workspace.paths.registry.name == "registry.jsonl"


def test_workspace_overrides(tmp_path: Path) -> None:
    manifest = {
        "workspace_id": "trace-mind:///custom",
        "name": "Custom",
        "directories": {
            "specs": "foo/specs",
            "artifacts": "data/artifacts",
            "reports": "log/reports",
        },
        "commit_policy": {
            "required": ["specs/**/*.yaml"],
            "optional": ["prompts/**/*"],
        },
        "languages": ["python", "rust"],
    }
    manifest_path = tmp_path / "tracemind.workspace.yaml"
    _write_manifest(manifest_path, manifest)
    workspace = load_workspace(tmp_path)
    assert workspace.paths.specs == (tmp_path / "foo/specs").resolve()
    assert workspace.paths.artifacts == (tmp_path / "data/artifacts").resolve()
    assert workspace.manifest.languages == ("python", "rust")
    assert workspace.manifest.commit_policy.required == ("specs/**/*.yaml",)
