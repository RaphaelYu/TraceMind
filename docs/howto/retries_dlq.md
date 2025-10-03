# Queue Retries & DLQ

This guide explains how to configure task retries and manage the dead letter
queue for TraceMind workers.

## Configure `trace_config.toml`

```toml
[retries.default]
max_attempts = 5        # total attempts before DLQ
base_ms = 200           # base backoff in milliseconds
factor = 2.0            # exponential factor
jitter_ms = 100         # random jitter per retry

[retries.flow."critical.flow"]
max_attempts = 3
base_ms = 100
factor = 1.5
```

The default section applies to every flow. Optional `retries.flow.<flow_id>`
entries override individual flows. Workers load the config automatically when
started via `tm workers start --config trace_config.toml`.

## Starting Workers with DLQ

```bash
tm workers start \
  --queue-dir data/queue \
  --idempotency-dir data/idempotency \
  --dlq-dir data/dlq \
  --config trace_config.toml \
  --drain-grace 15 \
  --runtime tm.app.wiring_flows:_runtime
```

Workers emit retry heartbeats and push terminal failures to the DLQ directory.
Sending `SIGINT` or `SIGTERM` triggers a graceful drain: workers stop leasing
new tasks, wait up to `--drain-grace` seconds for in-flight runs to complete,
flush checkpoints, and exit cleanly. Any tasks still running after the grace
period reappear once workers restart (visibility timeout ensures at-least-once
delivery).

## Inspect DLQ Entries

```bash
tm dlq ls --dlq-dir data/dlq --limit 10
```

Each entry is stored as JSON under `data/dlq/pending`. The listing prints the
flow id, attempt count, and the recorded error payload.

## Requeue or Purge

```bash
# Requeue a specific entry
tm dlq requeue dlq-1700000000000-12345 \
  --dlq-dir data/dlq \
  --queue-dir data/queue \
  --idempotency-dir data/idempotency \
  --config trace_config.toml

# Permanently remove an entry
tm dlq purge dlq-1700000000000-12345 --dlq-dir data/dlq
```

Requeued entries are copied back into the work queue with a fresh scheduled
timestamp, and the DLQ record moves to `archive/requeued`. Purged entries are
archived under `archive/purged` for audit purposes.

## Multi-Process Safety

The file-backed work queue uses advisory locks so multiple worker processes on
the same host can safely append and acknowledge tasks. If you experiment with
multi-host deployments, mount the queue directory on shared storage that
respects POSIX file locks. The memory backend remains single-process only.

## Metrics

When you expose the Prometheus exporter (`pip install -e .[prom]`), the worker
runtime publishes queue + worker metrics:

- `tm_queue_depth` / `tm_queue_lag_seconds` / `tm_queue_inflight`
- `tm_queue_enqueued_total` / `tm_queue_acked_total` / `tm_queue_nacked_total`
- `tm_queue_redelivered_total` / `tm_retries_total`
- `tm_dlq_total` / `tm_queue_idempo_hits_total`
- `tm_task_processing_ms` / `tm_end_to_end_ms`
- `tm_workers_live`

Use these gauges/counters to drive dashboards (depth vs inflight) and alerting
(e.g., sustained `tm_queue_lag_seconds` or DLQ growth).
