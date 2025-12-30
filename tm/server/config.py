"""Configuration helpers for the TraceMind TM server."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


@dataclass
class ServerConfig:
    base_dir: Path = Path(os.getenv("TM_SERVER_DATA_DIR", "tm_server"))
    registry_path: Path = Path(os.getenv("TM_SERVER_REGISTRY_PATH", ".tracemind/registry.jsonl"))
    record_path: Path = Path(os.getenv("TM_SERVER_RECORD_PATH", ".tracemind/controller_decide_records.json"))
    runs_dir: Path | None = None

    def __post_init__(self) -> None:
        self.base_dir = Path(self.base_dir)
        self.registry_path = Path(self.registry_path)
        self.record_path = Path(self.record_path)
        if self.runs_dir is None:
            self.runs_dir = self.base_dir / "runs"
        self.runs_dir = Path(self.runs_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.record_path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def runs_dir_path(self) -> Path:
        if self.runs_dir is None:
            self.runs_dir = self.base_dir / "runs"
        return self.runs_dir
