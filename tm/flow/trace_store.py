from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import orjson

from tm.storage.binlog import BinaryLogWriter


@dataclass
class TraceSpanLike:
    """Minimal span structure for flow execution tracing."""

    flow: str
    flow_id: str
    flow_rev: str
    run_id: str
    step: str
    step_id: str
    seq: int
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
            "flow_id": span.flow_id,
            "flow_rev": span.flow_rev,
            "run_id": span.run_id,
            "rule": span.rule or span.flow,
            "step": span.step,
            "step_id": span.step_id,
            "seq": span.seq,
            "t0": span.t0,
            "t1": span.t1,
            "error": span.error,
        }
        self._writer.append_many([("FlowTrace", orjson.dumps(payload))])
