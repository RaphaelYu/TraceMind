from __future__ import annotations

from dataclasses import dataclass
import queue
import threading
import time
from typing import Optional

try:  # pragma: no cover - optional dependency
    import orjson as _orjson

    def _dumps(payload: dict[str, object]) -> bytes:
        return _orjson.dumps(payload)

except ModuleNotFoundError:  # pragma: no cover - fallback
    import json as _json

    def _dumps(payload: dict[str, object]) -> bytes:
        return _json.dumps(payload).encode("utf-8")


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
    start_ts: float
    end_ts: float
    status: str
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    rule: Optional[str] = None


class FlowTraceSink:
    """Binary log sink for flow execution traces."""

    def __init__(
        self,
        dir_path: str,
        *,
        seg_bytes: int = 64_000_000,
        flush_interval: float = 0.05,
        max_batch: int = 128,
    ) -> None:
        self._writer = BinaryLogWriter(dir_path, seg_bytes=seg_bytes)
        self._queue: "queue.Queue[TraceSpanLike | object]" = queue.Queue()
        self._flush_interval = max(0.001, float(flush_interval))
        self._max_batch = max(1, int(max_batch))
        self._sentinel = object()
        self._closed = threading.Event()
        self._pending = 0
        self._pending_lock = threading.Lock()
        self._idle = threading.Event()
        self._idle.set()
        self._worker = threading.Thread(target=self._run, name="FlowTraceSinkWriter", daemon=True)
        self._worker.start()

    def append(self, span: TraceSpanLike) -> None:
        if self._closed.is_set():  # pragma: no cover - defensive guard
            return
        self._mark_enqueued(1)
        self._queue.put(span)

    def close(self, *, flush: bool = True, timeout: float | None = None) -> None:
        if self._closed.is_set():
            return
        self._closed.set()
        self._queue.put(self._sentinel)
        self._worker.join(timeout)
        if flush:
            self._idle.wait(timeout)
            try:
                self._writer.flush_fsync()
            except Exception:  # pragma: no cover - best effort
                pass
        try:
            self._writer.close()
        except Exception:  # pragma: no cover - best effort
            pass

    def _run(self) -> None:
        batch: list[TraceSpanLike] = []
        last_flush = time.monotonic()
        while True:
            timeout = max(self._flush_interval - (time.monotonic() - last_flush), 0.0)
            try:
                item = self._queue.get(timeout=timeout if timeout > 0 else self._flush_interval)
            except queue.Empty:
                item = None

            if item is self._sentinel:
                self._flush(batch)
                break

            if isinstance(item, TraceSpanLike):
                batch.append(item)

            now = time.monotonic()
            if batch and (len(batch) >= self._max_batch or item is None or (now - last_flush) >= self._flush_interval):
                self._flush(batch)
                batch.clear()
                last_flush = now

        # Drain any remaining spans enqueued after sentinel without blocking
        while True:  # pragma: no cover - safeguard
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            if isinstance(item, TraceSpanLike):
                self._flush([item])

    def _flush(self, batch: list[TraceSpanLike]) -> None:
        if not batch:
            return
        count = len(batch)
        records = [("FlowTrace", _dumps(self._encode(span))) for span in batch]
        try:
            self._writer.append_many(records)
            try:
                self._writer.flush_fsync()
            except Exception:  # pragma: no cover - best effort
                pass
        finally:
            self._mark_flushed(count)

    @staticmethod
    def _encode(span: TraceSpanLike) -> dict[str, object]:
        return {
            "flow": span.flow,
            "flow_id": span.flow_id,
            "flow_rev": span.flow_rev,
            "run_id": span.run_id,
            "rule": span.rule or span.flow,
            "step": span.step,
            "step_id": span.step_id,
            "seq": span.seq,
            "start_ts": span.start_ts,
            "end_ts": span.end_ts,
            "status": span.status,
            "error_code": span.error_code,
            "error_message": span.error_message,
        }

    def _mark_enqueued(self, count: int) -> None:
        if count <= 0:
            return
        with self._pending_lock:
            self._pending += count
            self._idle.clear()

    def _mark_flushed(self, count: int) -> None:
        if count <= 0:
            return
        with self._pending_lock:
            self._pending = max(0, self._pending - count)
            if self._pending == 0:
                self._idle.set()
