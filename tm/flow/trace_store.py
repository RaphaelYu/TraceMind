from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import orjson

from tm.storage.binlog import BinaryLogWriter


@dataclass
class TraceSpanLike:
    """Minimal span structure for flow execution tracing."""

    flow: str
    step: str
    t0: float
    t1: float
    error: Optional[str] = None
    rule: Optional[str] = None


class FlowTraceSink:
    """Binary log sink for flow execution traces."""

    def __init__(self, dir_path: str, seg_bytes: int = 64_000_000) -> None:
        self._writer = BinaryLogWriter(dir_path, seg_bytes=seg_bytes)

    def append(self, span: TraceSpanLike) -> None:
        payload = {
            "flow": span.flow,
            "rule": span.rule or span.flow,
            "step": span.step,
            "t0": span.t0,
            "t1": span.t1,
            "error": span.error,
        }
        self._writer.append_many([("FlowTrace", orjson.dumps(payload))])
