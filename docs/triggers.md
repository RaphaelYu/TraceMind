# Trigger Configuration & Runtime

TraceMind triggers let you enqueue flows automatically from external events without touching the CLI. The subsystem is intentionally stdlib-only so it works in offline or constrained environments and is easy to extend.

## 1. Configuration file (`triggers.yaml`)

Generate a starter file:

```bash
tm triggers init                 # writes triggers.yaml
```

Validate before running:

```bash
tm triggers validate --path triggers.yaml
```

Schema overview (YAML or JSON):

```yaml
version: 1
triggers:
  - id: hourly-report
    kind: cron
    cron: "0 * * * *"        # minute hour day month weekday
    timezone: local           # or UTC
    flow_id: flows/hourly.yaml
    input:
      mode: summary

  - id: webhook-orders
    kind: webhook
    route: "/hooks/orders"
    method: POST
    bind_host: 127.0.0.1
    bind_port: 8081
    allow_cleartext: true     # set false when using TLS
    secret: change-me         # shared secret via X-TraceMind-Secret header
    flow_id: flows/order-intake.yaml
    input:
      body: "{{ body }}"      # placeholders rendered from event context

  - id: ingest-folder
    kind: filesystem
    path: ./incoming
    pattern: "*.json"
    recursive: false
    interval_seconds: 5       # >= 0.5s
    flow_id: flows/file-import.yaml
    input:
      file_path: "{{ path }}"
```

Each `input` block is rendered with context such as:

- `trigger_id`, `trigger_kind`, `event_id`, `timestamp`
- Cron: `scheduled_at`
- Webhook: `method`, `path`, `query`, `headers`, `body`, `body_text`
- Filesystem: `path`, `name`, `parent`, `size`, `mtime`

`TriggerEvent` metadata is also attached under `_trigger` and as queue headers.

## 2. Running triggers

Standalone:

```bash
tm triggers run --config triggers.yaml \
  --queue-dir data/queue \
  --idempotency-dir data/idempotency \
  --dlq-dir data/dlq
```

With the daemon:

```bash
export TM_ENABLE_DAEMON=1
export TM_FILE_QUEUE_V2=1

# workers + triggers in one process
tm daemon start \
  --queue-dir data/queue \
  --idempotency-dir data/idempotency \
  --dlq-dir data/dlq \
  --enable-triggers \
  --triggers-config triggers.yaml
```

Status now reports the daemon PID and queue as before; the trigger metadata is stored in the daemon state file (`daemon.json`).

## 3. Security considerations

- Webhooks default to localhost and allow cleartext for home/lab setups. Provide `secret` and/or TLS certificate to secure production endpoints.
- Filesystem watcher uses polling with a minimum interval of 0.5s to avoid excessive disk churn. Adjust `interval_seconds` to balance latency vs. resource usage.
- Cron expressions support POSIX `*,-,/` syntax and `@every <seconds>` shortcuts.

## 4. Extending adapters

Adapters register via `tm.triggers.register_trigger_adapter(builder)` where `builder(config, handler)` returns a sequence of `_BaseAdapter` instances. Builders for cron, webhook, and filesystem are registered automatically, and you can add your own (e.g., Redis, MQTT, mDNS) from application code:

```python
from tm.triggers import register_trigger_adapter

def custom_builder(config_set, handler):
    ...  # yield adapter instances

register_trigger_adapter(custom_builder)
```

## 5. Event bus contract

Trigger adapters emit `TriggerEvent` objects:

```python
@dataclass(frozen=True)
class TriggerEvent:
    trigger_id: str
    kind: str
    flow_id: str
    payload: Mapping[str, object]
    headers: Mapping[str, str]
    idempotency_key: str | None = None
```

Events are enqueued via `TriggerQueueDispatcher`, reusing `TaskQueueManager` so idempotency, DLQ, and metrics stay consistent with the CLI/daemon path.

## 6. Troubleshooting

| Issue | Fix |
| ----- | --- |
| Webhook returns 401 | Ensure `X-TraceMind-Secret` matches `secret` in config. |
| Daemon exits immediately | Check `daemon.log` and confirm `TM_ENABLE_DAEMON=1`. |
| Filesystem trigger misses files | Increase `interval_seconds` or enable `recursive: true`. |
| Cron misfires | Validate cron expression syntax; cron and webhook adapters log to `tm.triggers.manager`. |

---

Need more automation? Register your own adapter builder, or run `tm triggers run` behind systemd/cron for specialized workflows.
