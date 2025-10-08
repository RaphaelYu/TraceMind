"""Human-in-the-loop approval queue."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from .audit import AuditTrail
from .config import HitlConfig
from pathlib import Path


class ApprovalDecision(Enum):
    APPROVE = "approve"
    DENY = "deny"
    TIMEOUT = "timeout"


@dataclass
class ApprovalRecord:
    approval_id: str
    flow: str
    step: str
    reason: str
    requested_by: str
    ttl_ms: int
    default_decision: ApprovalDecision
    actors: Tuple[str, ...]
    created_at: float
    payload: Mapping[str, object]
    status: str = "pending"
    decided_at: Optional[float] = None
    decided_by: Optional[str] = None
    note: Optional[str] = None

    def expired(self, *, now: Optional[float] = None) -> bool:
        if self.status != "pending":
            return False
        if self.ttl_ms <= 0:
            return False
        deadline = self.created_at + (self.ttl_ms / 1000.0)
        return (now or time.time()) >= deadline


class PendingApproval(Exception):
    def __init__(self, record: ApprovalRecord) -> None:
        super().__init__(record.reason)
        self.record = record

    def payload(self) -> Dict[str, object]:
        return {
            "status": "pending",
            "error_code": "APPROVAL_REQUIRED",
            "approval_id": self.record.approval_id,
            "reason": self.record.reason,
            "ttl_ms": self.record.ttl_ms,
            "default": self.record.default_decision.value,
            "actors": list(self.record.actors),
        }


class HitlManager:
    """Manage approval requests with optional persistence."""

    def __init__(self, config: HitlConfig, *, audit: Optional[AuditTrail] = None) -> None:
        self._config = config
        self._audit = audit
        self._enabled = config.enabled
        self._queue_limit = max(0, int(config.queue_size)) if config.queue_size else 0
        self._pending: Dict[str, ApprovalRecord] = {}
        self._store_path = Path(config.persistence_path) if config.persistence_path else None
        self._store_offset = 0
        if self._store_path and self._store_path.exists():
            self._replay_store()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def submit(
        self,
        *,
        flow: str,
        step: str,
        reason: str,
        requested_by: str,
        ttl_ms: Optional[int],
        default: str,
        actors: Iterable[str],
        payload: Mapping[str, object],
    ) -> ApprovalRecord:
        if not self._enabled:
            raise RuntimeError("HITL approvals are disabled")
        self._sync_store()
        if self._queue_limit and len(self._pending) >= self._queue_limit:
            raise RuntimeError("approval queue is full")

        approval_id = uuid.uuid4().hex
        normalized_default = ApprovalDecision.APPROVE if default.lower() == "approve" else ApprovalDecision.DENY
        ttl = ttl_ms if ttl_ms is not None else self._config.default_ttl_ms
        record = ApprovalRecord(
            approval_id=approval_id,
            flow=flow,
            step=step,
            reason=reason,
            requested_by=requested_by,
            ttl_ms=ttl,
            default_decision=normalized_default,
            actors=tuple(str(actor) for actor in actors if actor),
            created_at=time.time(),
            payload=dict(payload),
        )
        self._pending[approval_id] = record
        self._log("hitl_pending", record, extra={"status": "pending"})
        self._append_store(
            {
                "type": "pending",
                "approval_id": record.approval_id,
                "flow": record.flow,
                "step": record.step,
                "reason": record.reason,
                "requested_by": record.requested_by,
                "ttl_ms": record.ttl_ms,
                "default": record.default_decision.value,
                "actors": list(record.actors),
                "created_at": record.created_at,
                "payload": record.payload,
            }
        )
        return record

    def decide(self, approval_id: str, *, decision: str, actor: str, note: Optional[str] = None) -> ApprovalRecord:
        self._sync_store()
        record = self._pending.get(approval_id)
        if record is None:
            raise KeyError(f"Unknown approval_id '{approval_id}'")
        if record.status != "pending":
            return record
        normalized = _normalize_decision(decision)
        now = time.time()
        if record.expired(now=now):
            record.status = "timeout"
            record.decided_at = now
            record.decided_by = actor or "system"
            record.note = note
            self._log("hitl_timeout", record, extra={"decision": record.default_decision.value})
            raise TimeoutError("approval has expired")
        record.status = normalized.value
        record.decided_at = now
        record.decided_by = actor or "unknown"
        record.note = note
        self._log("hitl_decision", record, extra={"decision": record.status, "actor": record.decided_by})
        self._pending.pop(approval_id, None)
        self._append_store(
            {
                "type": "decision",
                "approval_id": approval_id,
                "decision": record.status,
                "actor": record.decided_by,
                "note": record.note,
                "ts": record.decided_at,
            }
        )
        return record

    def get(self, approval_id: str) -> Optional[ApprovalRecord]:
        self._sync_store()
        record = self._pending.get(approval_id)
        if record and record.expired():
            self._mark_expired(record)
            return None
        return record

    def pending(self) -> List[ApprovalRecord]:
        self._sync_store()
        now = time.time()
        expired: List[str] = []
        for approval_id, record in list(self._pending.items()):
            if record.expired(now=now):
                expired.append(approval_id)
                self._mark_expired(record)
        for approval_id in expired:
            self._pending.pop(approval_id, None)
        return list(self._pending.values())

    def _mark_expired(self, record: ApprovalRecord) -> None:
        record.status = "timeout"
        record.decided_at = time.time()
        record.decided_by = "system"
        self._log("hitl_timeout", record, extra={"decision": record.default_decision.value})

    def _log(self, event: str, record: ApprovalRecord, *, extra: Optional[Mapping[str, Any]] = None) -> None:
        if self._audit is None or not self._audit.enabled:
            return
        payload = {
            "approval_id": record.approval_id,
            "flow": record.flow,
            "step": record.step,
            "reason": record.reason,
            "status": record.status,
            "default": record.default_decision.value,
            "actors": list(record.actors),
        }
        if record.decided_by:
            payload["decided_by"] = record.decided_by
        if record.note:
            payload["note"] = record.note
        if extra:
            payload.update(dict(extra))
        self._audit.record(event, payload)

    def _append_store(self, entry: Mapping[str, Any]) -> None:
        if not self._store_path:
            return
        path = self._store_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False))
            fh.write("\n")
        self._store_offset = path.stat().st_size

    def _replay_store(self) -> None:
        if not self._store_path or not self._store_path.exists():
            return
        with self._store_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                self._apply_store_entry(entry, initial=True)
            self._store_offset = fh.tell()

    def _sync_store(self) -> None:
        if not self._store_path or not self._store_path.exists():
            return
        path = self._store_path
        with path.open("r", encoding="utf-8") as fh:
            fh.seek(self._store_offset)
            for line in fh:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                self._apply_store_entry(entry, initial=False)
            self._store_offset = fh.tell()

    def _apply_store_entry(self, entry: Mapping[str, Any], *, initial: bool) -> None:
        entry_type = entry.get("type")
        if entry_type == "pending":
            approval_id = entry.get("approval_id")
            if not isinstance(approval_id, str):
                return
            record = ApprovalRecord(
                approval_id=approval_id,
                flow=str(entry.get("flow", "unknown")),
                step=str(entry.get("step", "unknown")),
                reason=str(entry.get("reason", "approval required")),
                requested_by=str(entry.get("requested_by", "unknown")),
                ttl_ms=int(entry.get("ttl_ms", self._config.default_ttl_ms)),
                default_decision=(
                    ApprovalDecision.APPROVE
                    if str(entry.get("default", "approve")).lower() == "approve"
                    else ApprovalDecision.DENY
                ),
                actors=tuple(str(actor) for actor in entry.get("actors", []) if actor),
                created_at=float(entry.get("created_at", time.time())),
                payload=dict(entry.get("payload", {})),
            )
            if initial or approval_id not in self._pending:
                self._pending[approval_id] = record
        elif entry_type == "decision":
            approval_id = entry.get("approval_id")
            if not isinstance(approval_id, str):
                return
            record = self._pending.get(approval_id)
            if record is None:
                return
            decision = str(entry.get("decision", "deny"))
            record.status = decision
            record.decided_by = str(entry.get("actor", "unknown"))
            record.note = entry.get("note") if isinstance(entry.get("note"), str) else None
            record.decided_at = float(entry.get("ts", time.time()))
            self._pending.pop(approval_id, None)


def _normalize_decision(value: str) -> ApprovalDecision:
    lowered = value.lower().strip()
    if lowered in {"approve", "approved", "ok", "yes"}:
        return ApprovalDecision.APPROVE
    if lowered in {"deny", "denied", "reject", "rejected", "no"}:
        return ApprovalDecision.DENY
    raise ValueError(f"Unsupported decision '{value}'")


__all__ = [
    "ApprovalDecision",
    "ApprovalRecord",
    "HitlManager",
    "PendingApproval",
]
