from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping


@dataclass
class LlmConfigEntry:
    config_id: str
    model: str
    prompt_template_version: str
    prompt_version: str
    created_at: str
    model_id: str | None = None
    model_version: str | None = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "LlmConfigEntry":
        return cls(
            config_id=_require_str(data, "config_id"),
            model=_require_str(data, "model"),
            prompt_template_version=_require_str(data, "prompt_template_version"),
            prompt_version=_require_str(data, "prompt_version"),
            created_at=_require_str(data, "created_at"),
            model_id=_optional_str(data, "model_id"),
            model_version=_optional_str(data, "model_version"),
        )


def _require_str(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"missing or invalid '{key}'")
    return value


def _optional_str(data: Mapping[str, Any], key: str) -> str | None:
    value = data.get(key)
    return value if isinstance(value, str) and value else None


class LlmConfigRegistry:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def list(self) -> List[LlmConfigEntry]:
        entries: List[LlmConfigEntry] = []
        if not self.path.exists():
            return entries
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(data, Mapping):
                continue
            try:
                entries.append(LlmConfigEntry.from_mapping(data))
            except ValueError:
                continue
        return entries

    def get(self, config_id: str) -> LlmConfigEntry | None:
        for entry in self.list():
            if entry.config_id == config_id:
                return entry
        return None

    def add(
        self,
        *,
        model: str,
        prompt_template_version: str,
        prompt_version: str | None = None,
        model_id: str | None = None,
        model_version: str | None = None,
    ) -> LlmConfigEntry:
        prompt_version = prompt_version or prompt_template_version
        existing = next(
            (
                entry
                for entry in self.list()
                if entry.model == model
                and entry.prompt_template_version == prompt_template_version
                and entry.prompt_version == prompt_version
            ),
            None,
        )
        if existing is not None:
            return existing

        entry = LlmConfigEntry(
            config_id=f"llm-config-{uuid.uuid4().hex[:8]}",
            model=model,
            prompt_template_version=prompt_template_version,
            prompt_version=prompt_version,
            created_at=datetime.now(timezone.utc).isoformat(),
            model_id=model_id,
            model_version=model_version,
        )
        self._append(entry)
        return entry

    def _append(self, entry: LlmConfigEntry) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry.to_dict(), ensure_ascii=False))
            handle.write("\n")
