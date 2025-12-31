"""Helpers to bootstrap a TraceMind workspace with starter files."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from tm.utils.yaml import import_yaml
from tm.workspace.manifest import DEFAULT_DIRECTORIES

yaml = import_yaml()

REPO_ROOT = Path(__file__).resolve().parents[2]
GITIGNORE_TEMPLATE = REPO_ROOT / "specs" / "templates" / "workspace_gitignore.txt"

DEFAULT_COMMIT_POLICY = {
    "required": [
        "specs/**/*.yaml",
        "accepted/**/*.yaml",
    ],
    "optional": [
        "prompts/**/*",
        "specs/templates/**/*",
    ],
}

DEFAULT_CONTROLLER_BUNDLE = {
    "envelope": {
        "artifact_id": "tm-controller/demo/bundle",
        "artifact_type": "agent_bundle",
        "body_hash": "bundle-body-hash",
        "created_at": "2025-01-01T00:00:00Z",
        "created_by": "trace-mind",
        "envelope_hash": "bundle-envelope-hash",
        "meta": {
            "phase": "controller-demo",
            "policy": {
                "allow": [
                    "state:env.snapshot",
                    "artifact:proposed.plan",
                    "resource:inventory:update",
                ]
            },
        },
        "status": "accepted",
        "version": "v0",
    },
    "body": {
        "bundle_id": "tm-controller/demo",
        "agents": [
            {
                "agent_id": "tm-agent/controller-observe:0.1",
                "name": "controller-observe-mock",
                "version": "0.1",
                "runtime": {"kind": "python", "config": {}},
                "contract": {
                    "inputs": [],
                    "outputs": [
                        {
                            "ref": "state:env.snapshot",
                            "kind": "resource",
                            "mode": "write",
                            "required": True,
                            "schema": {"type": "object"},
                        }
                    ],
                    "effects": [
                        {
                            "name": "capture_snapshot",
                            "kind": "resource",
                            "target": "state:env.snapshot",
                            "idempotency": {"type": "keyed", "key_fields": ["snapshot_id"]},
                            "evidence": {"type": "hash", "path": "state:env.snapshot"},
                        }
                    ],
                },
                "config_schema": {"type": "object"},
                "evidence_outputs": [{"name": "snapshot", "description": "env snapshot evidence"}],
                "role": "observe",
            },
            {
                "agent_id": "tm-agent/controller-decide:0.1",
                "name": "controller-decide-mock",
                "version": "0.1",
                "runtime": {"kind": "python", "config": {}},
                "contract": {
                    "inputs": [
                        {
                            "ref": "state:env.snapshot",
                            "kind": "resource",
                            "mode": "read",
                            "required": True,
                            "schema": {"type": "object"},
                        }
                    ],
                    "outputs": [
                        {
                            "ref": "artifact:proposed.plan",
                            "kind": "artifact",
                            "mode": "write",
                            "required": True,
                            "schema": {"type": "object"},
                        }
                    ],
                    "effects": [
                        {
                            "name": "plan_decision",
                            "kind": "resource",
                            "target": "artifact:proposed.plan",
                            "idempotency": {"type": "keyed", "key_fields": ["plan_id"]},
                            "evidence": {"type": "hash", "path": "artifact:proposed.plan"},
                        }
                    ],
                },
                "config_schema": {"type": "object"},
                "evidence_outputs": [{"name": "plan", "description": "decision plan evidence"}],
                "role": "decide",
            },
            {
                "agent_id": "tm-agent/controller-act:0.1",
                "name": "controller-act-mock",
                "version": "0.1",
                "runtime": {"kind": "python", "config": {}},
                "contract": {
                    "inputs": [
                        {
                            "ref": "state:env.snapshot",
                            "kind": "resource",
                            "mode": "read",
                            "required": True,
                            "schema": {"type": "object"},
                        },
                        {
                            "ref": "artifact:proposed.plan",
                            "kind": "artifact",
                            "mode": "read",
                            "required": True,
                            "schema": {"type": "object"},
                        },
                    ],
                    "outputs": [
                        {
                            "ref": "artifact:execution.report",
                            "kind": "artifact",
                            "mode": "write",
                            "required": True,
                            "schema": {"type": "object"},
                        },
                        {
                            "ref": "state:act.result",
                            "kind": "resource",
                            "mode": "write",
                            "required": True,
                            "schema": {"type": "object"},
                        },
                    ],
                    "effects": [
                        {
                            "name": "apply_inventory",
                            "kind": "resource",
                            "target": "resource:inventory:update",
                            "idempotency": {"type": "keyed", "key_fields": ["idempotency_key"]},
                            "evidence": {"type": "hash", "path": "resource:inventory:update"},
                        }
                    ],
                },
                "config_schema": {"type": "object"},
                "evidence_outputs": [{"name": "act_report", "description": "execution evidence"}],
                "role": "act",
            },
        ],
        "plan": [
            {
                "step": "observe",
                "agent_id": "tm-agent/controller-observe:0.1",
                "phase": "run",
                "inputs": [],
                "outputs": ["state:env.snapshot"],
            },
            {
                "step": "decide",
                "agent_id": "tm-agent/controller-decide:0.1",
                "phase": "run",
                "inputs": ["state:env.snapshot"],
                "outputs": ["artifact:proposed.plan"],
            },
            {
                "step": "act",
                "agent_id": "tm-agent/controller-act:0.1",
                "phase": "run",
                "inputs": ["state:env.snapshot", "artifact:proposed.plan"],
                "outputs": ["artifact:execution.report", "state:act.result"],
            },
        ],
        "meta": {
            "phase": "controller-demo",
            "policy": {
                "allow": [
                    "state:env.snapshot",
                    "artifact:proposed.plan",
                    "resource:inventory:update",
                ]
            },
        },
    },
}

DEFAULT_INTENT_TEMPLATE = {
    "intent_id": "tm-intent/controller-demo",
    "title": "Controller demo intent",
    "description": "Demonstrates the workspace controller bundle using built-in mocks.",
    "language": "en",
    "goals": [
        {
            "name": "produce_inventory_report",
            "description": "Capture an env snapshot, plan a change, and emit an execution report.",
        }
    ],
    "preferences": [{"kind": "safety", "level": "high"}],
}


@dataclass(frozen=True)
class WorkspaceInitResult:
    workspace_id: str
    name: str
    manifest_path: Path
    directories: dict[str, Path]
    sample_controller_bundle: Path
    sample_intent: Path
    gitignore_snippet: str
    gitignore_path: Path | None


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower().strip()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
    normalized = normalized.strip("-")
    return normalized or "workspace"


def _write_document(path: Path, document: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if yaml is not None:
        with path.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(document, handle, sort_keys=True, allow_unicode=True)
        return
    path.write_text(json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_gitignore_snippet() -> str:
    try:
        return GITIGNORE_TEMPLATE.read_text(encoding="utf-8")
    except FileNotFoundError:  # pragma: no cover - template is committed
        return ""


def _resolve_directory(root: Path, value: str) -> Path:
    candidate = Path(value)
    return candidate if candidate.is_absolute() else (root / candidate)


def _append_gitignore(root: Path, snippet: str) -> Path:
    gitignore_path = root / ".gitignore"
    gitignore_path.parent.mkdir(parents=True, exist_ok=True)
    text = snippet.strip()
    if text:
        separator = "\n" if gitignore_path.exists() else ""
        with gitignore_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{separator}{text}\n")
    return gitignore_path


def initialize_workspace(
    root: Path | str,
    *,
    name: str,
    workspace_id: str | None = None,
    languages: Sequence[str] | None = None,
    directories: Mapping[str, str] | None = None,
    commit_policy: Mapping[str, Sequence[str]] | None = None,
    append_gitignore: bool = False,
) -> WorkspaceInitResult:
    root_path = Path(root)
    root_path.mkdir(parents=True, exist_ok=True)

    manifest_id = workspace_id or f"trace-mind:///{_slugify(name)}"
    manifest_languages = tuple(languages or ("python",))
    manifest_directories: dict[str, str] = dict(DEFAULT_DIRECTORIES)
    if directories:
        manifest_directories.update({key: value for key, value in directories.items() if value})

    manifest_commit = {
        "required": list((commit_policy or {}).get("required") or DEFAULT_COMMIT_POLICY["required"].copy()),
        "optional": list((commit_policy or {}).get("optional") or DEFAULT_COMMIT_POLICY["optional"].copy()),
    }

    manifest_payload = {
        "workspace_id": manifest_id,
        "name": name,
        "root": ".",
        "directories": manifest_directories,
        "commit_policy": manifest_commit,
        "languages": list(manifest_languages),
    }

    manifest_path = root_path / "tracemind.workspace.yaml"
    _write_document(manifest_path, manifest_payload)

    resolved_dirs: dict[str, Path] = {}
    for key, rel in manifest_directories.items():
        resolved = _resolve_directory(root_path, rel).resolve()
        resolved.mkdir(parents=True, exist_ok=True)
        resolved_dirs[key] = resolved

    specs_dir = resolved_dirs.get("specs", root_path / "specs")
    bundle_path = specs_dir / "controller_bundle.yaml"
    intent_path = specs_dir / "intents" / "example_intent.yaml"
    _write_document(bundle_path, DEFAULT_CONTROLLER_BUNDLE)
    _write_document(intent_path, DEFAULT_INTENT_TEMPLATE)

    snippet = _load_gitignore_snippet()
    gitignore_path = None
    if append_gitignore and snippet:
        gitignore_path = _append_gitignore(root_path, snippet)

    return WorkspaceInitResult(
        workspace_id=manifest_id,
        name=name,
        manifest_path=manifest_path.resolve(),
        directories={key: path for key, path in resolved_dirs.items()},
        sample_controller_bundle=bundle_path.resolve(),
        sample_intent=intent_path.resolve(),
        gitignore_snippet=snippet,
        gitignore_path=gitignore_path.resolve() if gitignore_path is not None else None,
    )
