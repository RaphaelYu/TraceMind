from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Dict

from tm.storage.binlog import BinaryLogWriter

from .policy_store import PolicyStore
from .proposals import Proposal


class AIController:
    """Manage policy proposals with audit logging."""

    def __init__(self, store: PolicyStore, audit_dir: str) -> None:
        self._store = store
        Path(audit_dir).mkdir(parents=True, exist_ok=True)
        self._writer = BinaryLogWriter(audit_dir)
        self._pending: Dict[str, Proposal] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def list_policies(self) -> Dict[str, object]:
        return {
            "version": self._store.version(),
            "policies": self._store.get(),
        }

    def list_pending(self) -> Dict[str, Dict[str, object]]:
        with self._lock:
            return {pid: proposal.to_dict() for pid, proposal in self._pending.items()}

    def submit(self, proposal: Proposal, *, actor: str) -> Dict[str, object]:
        with self._lock:
            self._pending[proposal.proposal_id] = proposal
        self._record("proposal_submitted", proposal=proposal.to_dict(), actor=actor)
        return {"status": "submitted", "id": proposal.proposal_id}

    def approve(self, proposal_id: str, *, actor: str, reason: str) -> Dict[str, object]:
        proposal = self._pop_pending(proposal_id)
        version = self._store.apply(proposal, actor=actor, reason=reason)
        self._record(
            "proposal_approved",
            proposal=proposal.to_dict(),
            actor=actor,
            reason=reason,
            version=version,
        )
        return {"status": "approved", "version": version}

    def reject(self, proposal_id: str, *, actor: str, reason: str) -> Dict[str, object]:
        proposal = self._pop_pending(proposal_id)
        self._record(
            "proposal_rejected",
            proposal=proposal.to_dict(),
            actor=actor,
            reason=reason,
        )
        return {"status": "rejected"}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _pop_pending(self, proposal_id: str) -> Proposal:
        with self._lock:
            if proposal_id not in self._pending:
                raise KeyError(f"Unknown proposal '{proposal_id}'")
            return self._pending.pop(proposal_id)

    def _record(self, event_type: str, **payload: object) -> None:
        event = {
            "ts": time.time(),
            "type": event_type,
            **payload,
        }
        data = json.dumps(event, ensure_ascii=False).encode("utf-8")
        self._writer.append_many([(event_type, data)])
