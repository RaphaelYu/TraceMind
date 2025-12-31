"""Tests for the TraceMind workspace initializer."""

from pathlib import Path

from tm.workspace import initialize_workspace


def test_initialize_workspace_writes_manifest_and_samples(tmp_path: Path) -> None:
    result = initialize_workspace(tmp_path, name="Demo Workspace")
    assert result.manifest_path.exists()
    assert result.sample_controller_bundle.exists()
    assert result.sample_intent.exists()
    assert (tmp_path / "tracemind.workspace.yaml").exists()
    assert (tmp_path / "specs" / "controller_bundle.yaml").exists()
    assert (tmp_path / "specs" / "intents" / "example_intent.yaml").exists()
    assert result.gitignore_path is None


def test_initialize_workspace_appends_gitignore(tmp_path: Path) -> None:
    result = initialize_workspace(tmp_path, name="Demo", append_gitignore=True)
    assert result.gitignore_path is not None
    content = result.gitignore_path.read_text(encoding="utf-8")
    assert result.gitignore_snippet.strip() in content
    assert result.gitignore_path.exists()
