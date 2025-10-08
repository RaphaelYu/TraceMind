from __future__ import annotations
import orjson
from .engine import TraceSpan
from tm.storage.binlog import BinaryLogWriter


class PipelineTraceSink:
    """Append trace spans into a dedicated binlog directory (e.g., /data/trace)."""

    def __init__(self, dir_path: str, seg_bytes: int = 64_000_000):
        self.writer = BinaryLogWriter(dir_path, seg_bytes=seg_bytes)

    def append(self, span: TraceSpan) -> None:
        payload = {
            "rule": span.rule,
            "step": span.step,
            "t0": span.t0,
            "t1": span.t1,
            "reads": span.reads,
            "writes": span.writes,
            "error": span.error,
            "inputs": span.inputs,
            "outputs": span.outputs,
        }
        self.writer.append_many([("PipelineTrace", orjson.dumps(payload))])
        # fsync cadence is handled by the global writer in the HTTP loop; if used standalone, you may
        # consider exposing a flush window as well.
