"""Prometheus text export helpers for the built-in metrics registry."""

from __future__ import annotations

from typing import Iterable, Mapping

from tm.obs.counters import Registry


def _format_labels(labels: Iterable[tuple[str, str]]) -> str:
    if not labels:
        return ""
    parts = [f"{key}={value!r}" for key, value in labels]
    return "{" + ",".join(parts) + "}"


def render_prometheus(snapshot: Mapping[str, Mapping[str, object]]) -> str:
    lines = []
    for metric_type, metrics in snapshot.items():
        if metric_type == "histograms":
            for name, buckets in metrics.items():
                lines.append(f"# TYPE {name} histogram")
                for label_key, samples in buckets.items():
                    for sample in samples:
                        labels = list(label_key) + [("le", str(sample.le))]
                        lines.append(f"{name}{_format_labels(labels)} {sample.count}")
        else:
            for name, samples in metrics.items():
                metric_kind = "counter" if metric_type == "counters" else "gauge"
                lines.append(f"# TYPE {name} {metric_kind}")
                for label_key, value in samples:
                    lines.append(f"{name}{_format_labels(label_key)} {value}")
    return "\n".join(lines) + "\n"


def mount_prometheus(app, registry: Registry) -> None:  # noqa: ANN001 - FastAPI app instance
    from fastapi import Response  # local import to avoid hard dependency at module load time

    @app.get("/metrics", include_in_schema=False)
    def _metrics() -> Response:
        snapshot = registry.snapshot()
        body = render_prometheus(snapshot)
        return Response(body, media_type="text/plain; version=0.0.4")
