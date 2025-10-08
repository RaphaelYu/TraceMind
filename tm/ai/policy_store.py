from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .proposals import Proposal


@dataclass
class PolicySnapshot:
    version: int
    policies: Dict[str, Any]
    history: List[Dict[str, Any]]


class PolicyStore:
    """Versioned JSON policy store with append-only audit history."""

    def __init__(self, path: str | os.PathLike[str]):
        self._path = Path(path)
        self._lock = threading.RLock()
        self._state = self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get(self, path: Optional[str] = None, *, default: Any = None) -> Any:
        with self._lock:
            if path is None:
                return json.loads(json.dumps(self._state.policies))
            parts = [p for p in path.split(".") if p]
            node = self._state.policies
            for segment in parts:
                if not isinstance(node, dict) or segment not in node:
                    return default
                node = node[segment]
            return json.loads(json.dumps(node))

    def history(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        with self._lock:
            data = list(self._state.history)
        if limit is not None:
            return data[-limit:]
        return data

    def version(self) -> int:
        with self._lock:
            return self._state.version

    def apply(
        self,
        proposal: Proposal,
        *,
        actor: str,
        reason: str,
    ) -> int:
        with self._lock:
            policies = json.loads(json.dumps(self._state.policies))
            for change in proposal.changes:
                change.apply(policies)

            version = self._state.version + 1
            entry = {
                "version": version,
                "applied_at": datetime.now(timezone.utc).isoformat(),
                "actor": actor,
                "reason": reason,
                "proposal": proposal.to_dict(),
            }
            history = self._state.history + [entry]

            snapshot = PolicySnapshot(version=version, policies=policies, history=history)
            self._write(snapshot)
            self._state = snapshot
            return version

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load(self) -> PolicySnapshot:
        if not self._path.exists():
            return PolicySnapshot(version=0, policies={}, history=[])
        with self._path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return PolicySnapshot(
            version=int(data.get("version", 0)),
            policies=data.get("policies", {}),
            history=data.get("history", []),
        )

    def _write(self, snapshot: PolicySnapshot) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = (
            self._path.with_suffix(self._path.suffix + ".tmp")
            if self._path.suffix
            else self._path.parent / (self._path.name + ".tmp")
        )
        payload = {
            "version": snapshot.version,
            "policies": snapshot.policies,
            "history": snapshot.history,
        }
        with temp_path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())
        temp_path.replace(self._path)


__all__ = ["PolicyStore", "PolicySnapshot"]
