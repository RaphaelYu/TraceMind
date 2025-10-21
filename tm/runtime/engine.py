from __future__ import annotations

from pathlib import Path
from typing import Optional

from tm.dsl.runtime import Engine, PythonEngine

from .config import RuntimeConfig, RuntimeConfigError, load_runtime_config
from .process_engine import ProcessEngine, ProcessEngineOptions

_CURRENT_CONFIG: RuntimeConfig = load_runtime_config()
_CURRENT_ENGINE: Engine = PythonEngine()


def get_engine() -> Engine:
    return _CURRENT_ENGINE


def runtime_config() -> RuntimeConfig:
    return _CURRENT_CONFIG


def refresh_engine(config_path: Optional[Path] = None) -> Engine:
    config = load_runtime_config(config_path)
    return configure_engine(config)


def configure_engine(config: RuntimeConfig) -> Engine:
    global _CURRENT_ENGINE, _CURRENT_CONFIG
    if config.engine == "python":
        _CURRENT_ENGINE = PythonEngine()
    elif config.engine == "proc":
        if config.executor_path is None:
            raise RuntimeConfigError(f"Process engine requires 'executor_path' in {config.config_path}")
        options = ProcessEngineOptions(executor_path=config.executor_path)
        _CURRENT_ENGINE = ProcessEngine(options)
    else:
        raise RuntimeConfigError(f"Unsupported engine '{config.engine}' in {config.config_path}")
    _CURRENT_CONFIG = config
    return _CURRENT_ENGINE


configure_engine(_CURRENT_CONFIG)


__all__ = ["get_engine", "runtime_config", "refresh_engine", "configure_engine"]
