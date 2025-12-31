"""Version and meta-data helpers for the tm-server API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import os
import subprocess

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover - safety fallback
    tomllib = None

SCHEMA_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "schemas" / "v0"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"


@dataclass(frozen=True)
class BuildInfo:
    git_commit: str | None
    build_time: str


def _read_project_version() -> str:
    if tomllib is None or not PYPROJECT_PATH.exists():
        return "0.0.0"
    try:
        with PYPROJECT_PATH.open("rb") as handle:
            data = tomllib.load(handle)
        project = data.get("project") or {}
        version = project.get("version")
        if version:
            return str(version)
        tool = data.get("tool", {})
        # Hatch uses [project], but fall back to tool.project version if available.
        for group in ("poetry", "hatch", "flit"):
            candidate = tool.get(group)
            if isinstance(candidate, dict) and candidate.get("version"):
                return str(candidate["version"])
    except Exception:
        return "0.0.0"
    return "0.0.0"


def _discover_schemas() -> list[str]:
    if not SCHEMA_DIR.exists():
        return []
    discovered: list[str] = []
    for entry in sorted(SCHEMA_DIR.glob("*.json")):
        discovered.append(f"{entry.stem}@v0")
    return discovered


def _git_commit() -> str | None:
    override = os.getenv("TM_SERVER_BUILD_COMMIT")
    if override:
        return override
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except Exception:
        return None


def _build_time() -> str:
    override = os.getenv("TM_SERVER_BUILD_TIME")
    if override:
        return override
    return datetime.now(timezone.utc).isoformat()


def get_api_meta() -> dict[str, object]:
    """Return the stable API meta payload for /api/v1/meta."""
    return {
        "api_version": "v1",
        "tm_core_version": _read_project_version(),
        "schemas_supported": _discover_schemas(),
        "build": BuildInfo(git_commit=_git_commit(), build_time=_build_time()).__dict__,
    }
