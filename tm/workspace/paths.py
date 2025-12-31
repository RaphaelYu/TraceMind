"""Defines standard workspace directory paths."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkspacePaths:
    """Resolved workspace directories relative to the workspace root."""

    root: Path
    specs: Path
    artifacts: Path
    reports: Path
    prompts: Path
    policies: Path

    @property
    def intents(self) -> Path:
        """Intents reside under the specs directory."""
        return self.specs / "intents"

    @property
    def accepted(self) -> Path:
        """Accepted artifacts live under the artifacts directory."""
        return self.artifacts / "accepted"

    @property
    def derived(self) -> Path:
        """Derived artifacts directory."""
        return self.artifacts / "derived"

    @property
    def gaps(self) -> Path:
        """Gap maps under reports."""
        return self.reports / "gaps"

    @property
    def backlog(self) -> Path:
        """Backlog items under reports."""
        return self.reports / "backlog"

    @property
    def registry(self) -> Path:
        """Registry file lives under artifacts."""
        return self.artifacts / "registry.jsonl"

    @property
    def llm_configs(self) -> Path:
        """LLM configuration registry stored under the artifacts directory."""
        return self.artifacts / "llm_configs.jsonl"
