from __future__ import annotations

from pathlib import Path

import pytest

from tm.runtime.config import RuntimeConfigError, load_runtime_config
from tm.runtime.engine import configure_engine, runtime_config, get_engine
from tm.dsl.runtime import PythonEngine


def test_load_runtime_config_defaults(tmp_path: Path) -> None:
    cfg = load_runtime_config()
    assert cfg.engine == "python"
    assert cfg.language == "python"
    assert cfg.plugins_language == "python"
    assert cfg.executor_path is None


def test_load_runtime_config_rejects_language_mismatch(tmp_path: Path) -> None:
    config_path = tmp_path / "runtime.yaml"
    config_path.write_text(
        """
runtime:
  engine: python
  language: python
  plugins_language: rust
        """.strip(),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeConfigError):
        load_runtime_config(config_path)


def test_configure_engine_unsupported_engine(tmp_path: Path) -> None:
    config_path = tmp_path / "runtime.yaml"
    config_path.write_text(
        """
runtime:
  engine: proc
  language: python
  plugins_language: python
        """.strip(),
        encoding="utf-8",
    )
    config = load_runtime_config(config_path)
    with pytest.raises(RuntimeConfigError):
        configure_engine(config)


def test_runtime_config_globals_are_python() -> None:
    cfg = runtime_config()
    assert cfg.engine == "python"
    assert isinstance(get_engine(), PythonEngine)
