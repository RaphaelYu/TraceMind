"""Workspace-local secret store helpers for TraceMind."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Sequence

from tm.utils.yaml import import_yaml

yaml = import_yaml()
DEFAULT_FILENAME = "secrets.yaml"


class SecretStore:
    """Minimal workspace-scoped secret registry stored under `.tracemind/`.

    The file is intentionally never committed.
    """

    def __init__(self, workspace_root: Path):
        self.workspace_root = Path(workspace_root)
        self._path = self.workspace_root / ".tracemind" / DEFAULT_FILENAME

    @property
    def path(self) -> Path:
        return self._path

    def list(self) -> list[str]:
        if not self._path.exists():
            return []
        try:
            text = self._path.read_text(encoding="utf-8")
        except OSError:
            return []
        if yaml is not None:
            payload = yaml.safe_load(text)
        else:
            payload = json.loads(text)
        if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
            return [str(item) for item in payload if item is not None]
        return []

    def add(self, secret: str) -> None:
        candidate = secret.strip()
        if not candidate:
            return
        current = self.list()
        if candidate in current:
            return
        entries = current + [candidate]
        self._write(entries)

    def _write(self, entries: Iterable[str]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = list(entries)
        if yaml is not None:
            with self._path.open("w", encoding="utf-8") as handle:
                yaml.safe_dump(data, handle, sort_keys=True, allow_unicode=True)
            return
        self._path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
