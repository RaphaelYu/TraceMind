"""Binary log exporter for metrics snapshots."""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Dict, List, Optional, Tuple

from tm.obs.counters import Registry
from tm.obs import counters
from tm.obs.exporters.file_exporter import _flatten_snapshot
from tm.storage.binlog import BinaryLogWriter


class BinlogExporter:
    def __init__(
        self,
        registry: Registry,
        *,
        dir_path: str,
        interval_s: float = 5.0,
        record_type: str = "MetricSample",
    ) -> None:
        self._registry = registry
        self._dir = dir_path
        self._interval = max(1.0, float(interval_s))
        self._record_type = record_type
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._writer: Optional[BinaryLogWriter] = None
        self._last_values: Dict[Tuple[str, str, Tuple[Tuple[str, str], ...]], float] = {}

    def start(self, registry: Optional[Registry] = None) -> None:
        if registry is not None:
            self._registry = registry
        if self._thread and self._thread.is_alive():
            return
        os.makedirs(self._dir, exist_ok=True)
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="metrics-binlog-exporter", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if not self._thread:
            return
        self._stop.set()
        self._thread.join(timeout=1.0)
        self._thread = None
        if self._writer and self._writer.fp:
            try:
                self._writer.fp.flush()
                self._writer.fp.close()
            except Exception:
                pass
        self._writer = None

    def _ensure_writer(self) -> BinaryLogWriter:
        if self._writer is None:
            self._writer = BinaryLogWriter(self._dir)
        return self._writer

    def _run(self) -> None:
        while not self._stop.is_set():
            started = time.time()
            try:
                self._export_snapshot()
            except Exception:
                pass
            remaining = self._interval - (time.time() - started)
            if remaining > 0:
                self._stop.wait(remaining)

    def export(self, snapshot: Optional[Dict[str, Dict[str, object]]] = None) -> None:
        snap = snapshot or self._registry.snapshot()
        self._write_entries(_flatten_snapshot(snap))

    def _export_snapshot(self) -> None:
        snapshot = self._registry.snapshot()
        self._write_entries(_flatten_snapshot(snapshot))

    def _write_entries(self, entries: List[Dict[str, object]]) -> None:
        if not entries:
            return
        writer = self._ensure_writer()
        frames: List[Tuple[str, bytes]] = []
        ts = time.time()
        for entry in entries:
            key = (
                entry["type"],
                entry["name"],
                tuple(sorted((str(k), str(v)) for k, v in entry["labels"].items())),
            )
            value = float(entry["value"])
            last = self._last_values.get(key, 0.0)
            record_value: Optional[float]
            if entry["type"] == "gauge":
                if last == value:
                    record_value = None
                else:
                    record_value = value
                    self._last_values[key] = value
            else:
                delta = value - last
                if delta <= 0:
                    self._last_values[key] = value
                    record_value = None
                else:
                    record_value = delta
                    self._last_values[key] = value
            if record_value is None:
                continue
            record = {
                "ts": ts,
                "name": entry["name"],
                "labels": entry["labels"],
                "value": record_value,
                "type": entry["type"],
            }
            encoded = json.dumps(record, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            frames.append((self._record_type, encoded))
        if frames:
            writer.append_many(frames)
            try:
                writer.flush_fsync()
            except Exception:
                pass


def maybe_enable_from_env(
    env: Optional[Dict[str, str]] = None,
    registry: Optional[Registry] = None,
) -> Optional[BinlogExporter]:
    env_map = env or os.environ
    dir_path = env_map.get("TRACE_METRICS_BINLOG_DIR")
    if not dir_path:
        return None
    interval = float(env_map.get("TRACE_METRICS_BINLOG_INTERVAL", "5"))
    registry = registry or counters.metrics
    exporter = BinlogExporter(registry, dir_path=dir_path, interval_s=interval)
    exporter.start(registry)
    return exporter
