# Scale & Reliability

Scale in TraceMind focuses on running sustained workloads with predictable latency, fast recovery, and observable behaviour. This guide collects the operational practices, CLI tooling, and metrics you need for v0.7 deployments.

---

## Topology Overview

### Single-host (official)
- **Layout**: one supervisor process (`tm workers start`) that forks multiple worker processes (spawned, not threads).
- **Shared state**: file-backed queue directory, idempotency cache directory, and DLQ directory mounted locally.
- **Signals**: `SIGTERM`/`SIGINT` triggers a graceful drain; heartbeats keep the supervisor aware of child health.

### Multi-host (experimental)
- **Shared storage**: mount the queue, idempotency, and DLQ directories on shared POSIX storage that honours advisory locks.
- **Coordination**: run one supervisor per host; each spawns local workers that cooperate through the shared queue files.
- **Caveats**: file locks and fsync cost increase under contention; keep queue segments on fast storage (NVMe or tmpfs + periodic sync).

---

## Queue Backends

### File backend (default)
- **Segments**: tasks append to `segment-000001.log` style JSONL files with sidecar index files retaining acked offsets.
- **Rotation**: controlled by `segment_max_mb` (default 64 MB). Rotation prevents unbounded files and aids recovery.
- **Leases**: visibility timeouts (default `--lease-ms 30000`) stored per task; expired leases re-enter the ready heap.
- **Metadata**: `queue.meta` + `queue.offset` track active segment and next offset for crash-safe restarts.

### Memory backend (development)
- Single-process heap with the same leasing semantics.
- No durability or cross-process safety; use for unit tests only.
- Enforcing `-n 1` ensures you do not accidentally run multiple workers with this backend.

---

## Task Envelope & Idempotency

- Every enqueue builds a `TaskEnvelope` with `flow_id`, `input`, `headers`, `scheduled_at`, and optional trace metadata.
- Idempotency keys live in `headers.idempotency_key`. Duplicate keys return cached results without enqueueing.
- Persistence: `IdempotencyStore` snapshots to `idempotency.json` (LRU + TTL). Default TTL is configurable via `WorkerOptions.result_ttl`.
- Delivery semantics: at-least-once. If a worker crashes mid-task, the lease expires and the task becomes visible again.

---

## Worker Lifecycle

- `tm workers start` wraps `TaskWorkerSupervisor.run_forever()`; the supervisor writes a PID file (default `tm-workers.pid`).
- Heartbeats: workers send heartbeats over a control pipe. Stale workers are terminated and respawned automatically.
- Graceful drain: `tm workers stop` (or `SIGTERM`) flips a drain flag, stops leasing new work, waits `--drain-grace` seconds, then exits.
- Signals: built-in handler catches `SIGTERM` and `SIGINT`. `SIGKILL` should be avoided because it skips drain and PID cleanup.

---

## CLI Reference

| Command | Purpose |
| --- | --- |
| `tm workers start -n 4 --queue file --lease-ms 30000` | Launch worker pool (writes PID file, installs signal handlers). |
| `tm workers stop` | Reads the PID file and sends `SIGTERM` for a graceful drain. |
| `tm enqueue <flow.yaml> -i '{"k":"v"}' --idempotency-key KEY` | Enqueue a JSON payload; if `<flow.yaml>` exists, `flow.id` is used automatically. |
| `tm queue stats --queue file` | Show depth, inflight count, and lag without touching leases. Use `--json` for scripts. |
| `tm dlq ls --since 10m --limit 5` | List recent DLQ entries (JSON lines for piping). |
| `tm dlq requeue dlq-1700* --all` | Requeue matching DLQ entries (glob or exact id). |
| `tm dlq purge dlq-1700* --yes` | Archive/purge matching entries; guarded prompt unless `--yes` is supplied. |

Run `tm <command> --help` for detailed option docs and embedded examples.

---

## Copy-paste Demo

```bash
# Start workers
TM_LOG=info tm workers start -n 4 --queue file --lease-ms 30000 &

# Enqueue 1000 CPU-light tasks
for i in {1..1000}; do tm enqueue flows/hello.yaml -i '{"name":"w'$i'"}'; done

# Live queue stats
tm queue stats

# Retry/DLQ demo — simulate failures by input flag/env within your step
export FAIL_RATE=0.05
# (run some tasks…)

tm dlq ls | head        # Inspect
# Requeue a subset by id/prefix/predicate (implementation-specific)
tm dlq requeue <task-id>

# Graceful drain
tm workers stop
```

During the run, `tm queue stats` should show `depth` trending down while `inflight` hovers around the worker count. DLQ commands let you inspect and requeue any failures introduced by `FAIL_RATE`.

---

## Configuration Snippet

```toml
[queue]
backend = "file"            # or "memory"
segment_max_mb = 64
lease_ms = 30000

[retries.default]
max_attempts = 5
base_ms = 200
factor = 2.0
jitter_ms = 50

[idempotency]
result_ttl_sec = 3600
```

- `segment_max_mb`: controls rotation. Smaller values reduce replay time; larger values reduce filesystem churn.
- Retry config feeds `load_retry_policy`. Per-flow overrides live under `retries.flow.<flow_id>`.
- `result_ttl_sec` lines up with the `--result-ttl` CLI flag for workers.

---

## Retries & Dead Letters

- Workers consult the retry policy each time a flow signals failure. Delays use exponential backoff plus jitter.
- After `max_attempts`, the envelope is moved to the DLQ directory (`pending/`).
- `tm dlq ls` prints each entry as JSON for easy filtering (`jq`, `grep`).
- `tm dlq requeue` copies the original payload back into the queue and archives the DLQ record under `archive/requeued/`.
- `tm dlq purge` archives to `archive/purged/`. The guarded prompt prevents accidental deletions.

See [`docs/howto/retries_dlq.md`](howto/retries_dlq.md) for extended walk-throughs.

---

## Recovery & Safeguards

- **Cold start**: the file queue rebuilds its in-memory index by scanning segment logs and `.idx` files; unacked records become visible again.
- **Index rebuild**: if an `.idx` file is missing or corrupt, the loader recreates it by replaying the segment.
- **Idempotency snapshots**: `idempotency.json` is rewritten atomically (`.tmp` + `os.replace`). If parsing fails, the store starts empty.
- **Corruption handling**: malformed log lines or DLQ payloads are skipped with warnings so you can repair offline.
- **Checkpoints**: workers fsync queue segments on rotate and optionally on each append (see `fsync_on_put`).

---

## Metrics & SLO Hints

**Gauges**: `tm_queue_depth`, `tm_queue_lag_seconds`, `tm_queue_inflight`, `tm_workers_live`

**Counters**: `tm_queue_enqueued_total`, `tm_queue_acked_total`, `tm_queue_nacked_total`, `tm_queue_redelivered_total`, `tm_retries_total`, `tm_dlq_total`, `tm_queue_idempo_hits_total`

**Histograms**: `tm_task_processing_ms`, `tm_end_to_end_ms`

SLO ideas:
- Alert if `tm_queue_lag_seconds` crosses a flow-specific threshold for more than 5 minutes.
- Compare `tm_dlq_total` vs `tm_queue_enqueued_total` to detect failure spikes.
- Dashboard layout: (1) gauges for depth/lag/inflight, (2) histograms for processing vs end-to-end latency, (3) counters for retries & DLQ.

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
| --- | --- | --- |
| Queue depth grows but workers idle | Supervisor not running or workers crashed | Re-run `tm workers start`; inspect logs for restart loops. |
| `tm enqueue` reports duplicate | Reused `idempotency_key` | Provide a unique key or prune the idempotency cache. |
| DLQ fills rapidly | Flow errors or retry policy too aggressive | Inspect with `tm dlq ls`, adjust `[retries]` config or fix flow logic. |
| `tm queue stats` lag keeps increasing | Tasks blocked on upstream dependency | Increase worker count or reduce external latency; monitor `tm_task_processing_ms`. |
| Workers exit immediately | Missing runtime factory | Pass `--runtime tm.app.wiring_flows:_runtime` or your project runtime. |

---

## Additional Resources

- [`docs/howto/retries_dlq.md`](howto/retries_dlq.md) – deep dive into retries & DLQ
- [`docs/overview.md`](overview.md) – high-level system tour
- `tm workers --help`, `tm queue --help`, `tm dlq --help` – CLI reminders with embedded examples
