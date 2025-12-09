"""Periodic exporter that persists metric snapshots to disk."""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional, Iterable

from tm.obs.counters import Registry, _MetricsProxy
from tm.obs import counters


def _flatten_snapshot(snapshot: Dict[str, Dict[str, object]]) -> List[Dict[str, object]]:
    entries: List[Dict[str, object]] = []
    for metric_type, named_metrics in snapshot.items():
        if not isinstance(named_metrics, dict):
            continue
        if metric_type == "histograms":
            for name, buckets in named_metrics.items():
                if not isinstance(buckets, dict):
                    continue
                for label_key, bucket_list in buckets.items():
                    if not isinstance(label_key, Iterable):
                        continue
                    base_labels = dict(label_key)
                    if not isinstance(bucket_list, Iterable):
                        continue
                    for bucket in bucket_list:
                        count = getattr(bucket, "count", None)
                        if count is None:
                            continue
                        labels = dict(base_labels)
                        labels["le"] = str(getattr(bucket, "le", ""))
                        entries.append(
                            {
                                "type": "hist",
                                "name": name,
                                "labels": labels,
                                "value": count,
                            }
                        )
        else:
            metric_kind = "counter" if metric_type == "counters" else "gauge"
            for name, samples in named_metrics.items():
                if not isinstance(samples, Iterable):
                    continue
                for sample in samples:
                    if not isinstance(sample, tuple) or len(sample) != 2:
                        continue
                    label_key, value = sample
                    if not isinstance(label_key, Iterable):
                        continue
                    entries.append(
                        {
                            "type": metric_kind,
                            "name": name,
                            "labels": dict(label_key),
                            "value": value,
                        }
                    )
    return entries


class FileExporter:
    """Background worker that stores registry snapshots in NDJSON or CSV."""

    def __init__(
        self,
        registry: Registry | _MetricsProxy,
        *,
        dir_path: str,
        fmt: str = "ndjson",
        interval_s: float = 5.0,
    ) -> None:
        self._registry = registry
        self._dir = dir_path
        self._fmt = fmt.lower()
        if self._fmt not in {"ndjson", "csv"}:
            raise ValueError("fmt must be 'ndjson' or 'csv'")
        self._interval = max(1.0, float(interval_s))
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def start(self, registry: Optional[Registry | _MetricsProxy] = None) -> None:
        if registry is not None:
            self._registry = registry
        if self._thread and self._thread.is_alive():
            return
        os.makedirs(self._dir, exist_ok=True)
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="metrics-file-exporter", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if not self._thread:
            return
        self._stop.set()
        self._thread.join(timeout=1.0)
        self._thread = None

    def _run(self) -> None:
        while not self._stop.is_set():
            started = time.time()
            try:
                self._export_snapshot()
            except Exception:
                # swallow errors to keep exporter alive
                pass
            remaining = self._interval - (time.time() - started)
            if remaining > 0:
                self._stop.wait(remaining)

    def export(self, snapshot: Optional[Dict[str, Dict[str, object]]] = None) -> None:
        snap = snapshot or self._registry.snapshot()
        self._write_entries(_flatten_snapshot(snap))

    def _export_snapshot(self) -> None:
        snapshot = self._registry.snapshot()
        entries = _flatten_snapshot(snapshot)
        if not entries:
            return
        self._write_entries(entries)

    def _write_entries(self, entries: List[Dict[str, object]]) -> None:
        filename = self._current_filename()
        if self._fmt == "ndjson":
            with open(filename, "a", encoding="utf-8") as fh:
                for entry in entries:
                    fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        else:
            # csv format with simple schema: type,name,labels,value
            lines = []
            for entry in entries:
                labels_obj = entry.get("labels", {})
                labels_dict = labels_obj if isinstance(labels_obj, dict) else {}
                label_str = ";".join(f"{k}={v}" for k, v in sorted(labels_dict.items()))
                lines.append(f"{entry.get('type')},{entry.get('name')},{label_str},{entry.get('value')}")
            with open(filename, "a", encoding="utf-8") as fh:
                if os.path.getsize(filename) == 0:
                    fh.write("type,name,labels,value\n")
                fh.write("\n".join(lines) + "\n")

    def _current_filename(self) -> str:
        ts = datetime.utcnow().strftime("%Y%m%d%H")
        ext = "ndjson" if self._fmt == "ndjson" else "csv"
        return os.path.join(self._dir, f"metrics-{ts}.{ext}")


def maybe_enable_from_env(
    env: Optional[Dict[str, str]] = None,
    registry: Optional[Registry | _MetricsProxy] = None,
) -> Optional[FileExporter]:
    env_map = env or os.environ
    dir_path = env_map.get("TRACE_METRICS_FILE_DIR")
    if not dir_path:
        return None
    fmt = env_map.get("TRACE_METRICS_FILE_FMT", "ndjson")
    interval = float(env_map.get("TRACE_METRICS_FILE_INTERVAL", "5"))
    registry = registry or counters.metrics
    exporter = FileExporter(registry, dir_path=dir_path, fmt=fmt, interval_s=interval)
    exporter.start(registry)
    return exporter
