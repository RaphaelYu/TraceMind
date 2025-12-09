from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:  # pragma: no cover - optional dependency
    import yaml  # type: ignore[import-untyped]
except ModuleNotFoundError:  # pragma: no cover
    yaml = None


class RuntimeConfigError(RuntimeError):
    """Raised when runtime configuration cannot be loaded."""


@dataclass(frozen=True)
class RuntimeConfig:
    engine: str
    language: str
    plugins_language: str
    executor_path: Optional[Path]
    config_path: Path

    def requires_executor(self) -> bool:
        return self.engine not in {"python"}


def _default_config_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "runtime.yaml"


def load_runtime_config(path: Optional[Path] = None) -> RuntimeConfig:
    resolved_path = Path(path) if path is not None else _default_config_path()
    if not resolved_path.exists() or yaml is None:
        return RuntimeConfig(
            engine="python",
            language="python",
            plugins_language="python",
            executor_path=None,
            config_path=resolved_path,
        )

    try:
        data = yaml.safe_load(resolved_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # pragma: no cover - propagate parse errors
        raise RuntimeConfigError(f"Failed to load runtime config at {resolved_path}: {exc}") from exc

    if not isinstance(data, dict):
        raise RuntimeConfigError(f"Runtime config {resolved_path} must be a mapping")

    runtime_section = data.get("runtime")
    if not isinstance(runtime_section, dict):
        raise RuntimeConfigError(f"Runtime config {resolved_path} missing 'runtime' section")

    engine = str(runtime_section.get("engine", "python")).strip() or "python"
    language = str(runtime_section.get("language", "python")).strip() or "python"
    plugins_language = str(runtime_section.get("plugins_language", language)).strip() or language

    executor_raw = runtime_section.get("executor_path")
    executor_path = None
    if isinstance(executor_raw, str) and executor_raw.strip():
        executor_path = Path(executor_raw).expanduser()

    if plugins_language != language:
        raise RuntimeConfigError(
            f"Runtime config {resolved_path} must align runtime language '{language}' with plugins '{plugins_language}'"
        )

    return RuntimeConfig(
        engine=engine,
        language=language,
        plugins_language=plugins_language,
        executor_path=executor_path,
        config_path=resolved_path,
    )


__all__ = ["RuntimeConfig", "RuntimeConfigError", "load_runtime_config"]
