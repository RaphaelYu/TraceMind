from __future__ import annotations

import json
import os
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Tuple, cast

from .api import KStore, register_driver, resolve_path


def _ensure_mapping(value: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError("kstore values must be mappings")
    return {str(key): val for key, val in value.items()}


class JsonlKStore(KStore):
    """Append-only JSON Lines knowledge store with atomic updates."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self._path = Path(path)
        self._records: list[dict[str, Any]] = []
        self._state: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._load()

    def _load(self) -> None:
        try:
            with self._path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    record = json.loads(line)
                    if isinstance(record, dict):
                        record_dict = dict(record)
                        self._records.append(record_dict)
                        self._apply_record(record_dict)
        except FileNotFoundError:
            return

    def _apply_record(self, record: Mapping[str, Any]) -> None:
        op = record.get("op")
        key = record.get("key")
        if not isinstance(key, str):
            return
        if op == "put":
            value = record.get("value")
            if isinstance(value, Mapping):
                self._state[key] = _ensure_mapping(cast(Mapping[str, Any], value))
            else:
                raise TypeError("jsonl record 'value' must be a mapping")
        elif op == "delete":
            self._state.pop(key, None)

    def put(self, key: str, value: Mapping[str, Any]) -> None:
        if not isinstance(key, str):
            raise TypeError("key must be a string")
        record = {"op": "put", "key": key, "value": _ensure_mapping(value)}
        with self._lock:
            prev = self._state.get(key)
            self._records.append(record)
            self._state[key] = _ensure_mapping(cast(Mapping[str, Any], record["value"]))
            try:
                self._flush()
            except Exception:
                self._records.pop()
                if prev is None:
                    self._state.pop(key, None)
                else:
                    self._state[key] = dict(prev)
                raise

    def get(self, key: str) -> Mapping[str, Any] | None:
        if not isinstance(key, str):
            raise TypeError("key must be a string")
        with self._lock:
            value = self._state.get(key)
            return dict(value.items()) if value is not None else None

    def scan(self, prefix: str) -> Iterable[Tuple[str, Mapping[str, Any]]]:
        prefix = prefix or ""
        with self._lock:
            items = [(k, dict(v.items())) for k, v in self._state.items() if k.startswith(prefix)]
        items.sort(key=lambda item: item[0])
        return items

    def delete(self, key: str) -> bool:
        if not isinstance(key, str):
            raise TypeError("key must be a string")
        record = {"op": "delete", "key": key}
        with self._lock:
            existed = key in self._state
            prev = self._state.get(key)
            self._records.append(record)
            self._state.pop(key, None)
            try:
                self._flush()
            except Exception:
                self._records.pop()
                if prev is not None:
                    self._state[key] = dict(prev.items())
                raise
        return existed

    def close(self) -> None:
        # No persistent handles to close, but method included for protocol symmetry.
        return None

    def _flush(self) -> None:
        parent = self._path.parent
        if str(parent):
            parent.mkdir(parents=True, exist_ok=True)
        tmp_name = f".{self._path.name}.tmp-{uuid.uuid4().hex}"
        tmp_path = parent / tmp_name if str(parent) else Path(tmp_name)
        with tmp_path.open("w", encoding="utf-8") as fh:
            for record in self._records:
                fh.write(json.dumps(record, separators=(",", ":"), ensure_ascii=True))
                fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, self._path)


def _factory(_: str, parsed) -> KStore:
    path = resolve_path(parsed)
    return JsonlKStore(path)


register_driver("jsonl", _factory)

__all__ = ["JsonlKStore"]
