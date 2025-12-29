from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Mapping


@dataclass(frozen=True)
class EvidenceRecord:
    kind: str
    payload: Mapping[str, Any]


class EvidenceRecorder:
    """Collects evidence entries emitted by a runtime agent."""

    def __init__(self) -> None:
        self._records: List[EvidenceRecord] = []

    def record(self, kind: str, payload: Mapping[str, Any]) -> None:
        self._records.append(EvidenceRecord(kind=kind, payload=dict(payload)))

    def records(self) -> List[EvidenceRecord]:
        return list(self._records)

    def clear(self) -> None:
        self._records.clear()
