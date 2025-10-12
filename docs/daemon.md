# Daemon Mode (Opt-In)

TraceMind's daemon mode lets you enqueue work without blocking the CLI. A background process owns the task queue, idempotency store, and worker pool, while the `tm` CLI becomes a thin client that submits tasks and reports status.

> **Status**: opt-in (feature flagged). Existing synchronous flows continue to work without the daemon.

---

## 1. Enable feature flags

```bash
export TM_ENABLE_DAEMON=1
export TM_FILE_QUEUE_V2=1  # recommended for durable queue semantics
```

- `TM_ENABLE_DAEMON` gates the CLI subcommands (`tm daemon *`) and `tm run --detached`.
- `TM_FILE_QUEUE_V2` activates stricter file queue locking and persistence (required for reliable ack/resume on Windows).

You can set these in your shell profile or CI environment. Without the flag, `tm daemon` exits immediately so legacy behavior is unchanged.

---

## 2. Directory layout

The daemon relies on three directories (defaults shown):

| Purpose           | Flag / Option         | Default         |
| ----------------- | --------------------- | --------------- |
| Queue segments    | `--queue-dir`         | `data/queue`    |
| Idempotency cache | `--idempotency-dir`   | `data/idempotency` |
| Dead letter queue | `--dlq-dir`           | `data/dlq`      |

`tm daemon start` creates the directories if they do not exist. On Windows, keep these on a local drive (avoid network shares) to ensure file locks work correctly.

The daemon also writes metadata into `~/.trace-mind/daemon` by default:

- `daemon.pid` — PID of the last launched daemon
- `daemon.json` — JSON blob with PID, queue path, and metadata
- `daemon.log` — log file if you do not pass `--inherit-logs`

Override with `--state-dir` or `$TM_DAEMON_STATE_DIR`.

---

## 3. Typical workflow

```bash
# 1. Launch daemon (spawns workers via tm workers start)
tm daemon start \
  --queue-dir data/queue \
  --idempotency-dir data/idempotency \
  --dlq-dir data/dlq \
  --workers 2

# 2. Submit detached runs (non-blocking)
tm run flows/hello.yaml --detached -i '{"name":"async"}'
tm enqueue flows/other.yaml -i '{"name":"queued"}'

# 3. Observe status (human friendly)
tm daemon ps

# 4. Or fetch JSON for scripting/monitoring
tm daemon ps --json | jq '.queue'

# 5. Stop when finished (default timeout=10s, escalate to SIGKILL afterward)
tm daemon stop

# Optional: run trigger adapters in the same process
tm daemon start \
  --queue-dir data/queue \
  --idempotency-dir data/idempotency \
  --dlq-dir data/dlq \
  --enable-triggers \
  --triggers-config triggers.yaml
```

If `tm daemon start` is invoked twice, the second call reports the existing PID. `tm daemon stop` exits cleanly if the daemon is not running.

---

## 4. Smoke script (CI & local)

`scripts/daemon_smoke.sh` performs the following sequence and cleans up on exit:

1. Enable both feature flags.
2. Launch daemon with temporary directories.
3. Run `tm run --detached` against a sample recipe (JSON stub).
4. Call `tm daemon ps --json` and check for pending/inflight counts.
5. Stop the daemon gracefully.

To include triggers in the smoke run:

```bash
scripts/daemon_smoke.sh --triggers triggers.yaml
```

Run it locally with `bash scripts/daemon_smoke.sh`. CI executes the same script on pull requests to guard against regressions. If the script fails it prints the daemon log path for debugging.

---

## 5. Troubleshooting

| Symptom | Fix |
| ------- | --- |
| `tm daemon start` exits immediately | Ensure `TM_ENABLE_DAEMON=1`. Also check logs at `<state-dir>/daemon.log`. |
| Detached run never shows up | Confirm daemon is running (`tm daemon ps`), feature flags are set, and queue directories are writable. Set `TM_FILE_QUEUE_V2=1` for stronger persistence. |
| `Permission denied` on Windows | Keep queue directories on NTFS, avoid WSL path crossovers, and ensure the account launching the daemon has full control. |
| Daemon log missing | Use `--log-file` to specify path or `--inherit-logs` to print to stdout/stderr. |
| CI smoke fails | Inspect CI artifact `daemon.log`; rerun smoke script locally. |

---

## 6. Advanced tweaks

- **Workers runtime**: `--runtime module:factory` to pick a different worker entry point.
- **Log handling**: `--inherit-logs` to stream logs instead of locking to a file (useful in containers).
- **No-force stop**: pass `--no-force` to avoid SIGKILL escalation and handle your own shutdown.
- **Manual queue inspection**: `tm queue stats --queue-dir data/queue` still works even when daemon runs.

---

## 7. Compatibility notes

- The daemon + detached runs require POSIX or Windows environments where subprocesses and file locks are available. It is not supported on read-only filesystems.
- Feature flags keep the functionality off by default; existing scripts and flows keep current semantics.
- `TM_FILE_QUEUE_V2` improves durability for daemon workloads; you can test V2 in isolation before enabling it in production.
