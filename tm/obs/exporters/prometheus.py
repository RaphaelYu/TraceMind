"""Prometheus text export helpers for the built-in metrics registry."""

from __future__ import annotations

from typing import Iterable, Mapping, Union

from tm.obs.counters import Registry, _MetricsProxy


def _format_labels(labels: Iterable[tuple[str, str]]) -> str:
    if not labels:
        return ""
    parts = [f"{key}={value!r}" for key, value in labels]
    return "{" + ",".join(parts) + "}"


def render_prometheus(snapshot: Mapping[str, Mapping[str, object]]) -> str:
    lines = []
    for metric_type, metrics in snapshot.items():
        if not isinstance(metrics, Mapping):
            continue
        if metric_type == "histograms":
            for name, buckets in metrics.items():
                if not isinstance(buckets, Mapping):
                    continue
                lines.append(f"# TYPE {name} histogram")
                for label_key, samples in buckets.items():
                    if not isinstance(label_key, Iterable):
                        continue
                    if not isinstance(samples, Iterable):
                        continue
                    for sample in samples:
                        bucket_labels = list(label_key) + [("le", str(getattr(sample, "le", "")))]
                        count = getattr(sample, "count", None)
                        if count is None:
                            continue
                        lines.append(f"{name}{_format_labels(bucket_labels)} {count}")
        else:
            for name, samples in metrics.items():
                if not isinstance(samples, Iterable):
                    continue
                metric_kind = "counter" if metric_type == "counters" else "gauge"
                lines.append(f"# TYPE {name} {metric_kind}")
                for sample in samples:
                    if not isinstance(sample, tuple) or len(sample) != 2:
                        continue
                    label_key, value = sample
                    if not isinstance(label_key, Iterable):
                        continue
                    lines.append(f"{name}{_format_labels(label_key)} {value}")
    return "\n".join(lines) + "\n"


RegistryLike = Union[Registry, _MetricsProxy]


def mount_prometheus(app, registry: RegistryLike) -> None:  # noqa: ANN001 - FastAPI app instance
    from fastapi import Response  # local import to avoid hard dependency at module load time

    @app.get("/metrics", include_in_schema=False)
    def _metrics() -> Response:
        snapshot = registry.snapshot()
        body = render_prometheus(snapshot)
        return Response(body, media_type="text/plain; version=0.0.4")
