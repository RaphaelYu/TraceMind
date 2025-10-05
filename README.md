[![PyPI](https://img.shields.io/pypi/v/trace-mind.svg)](#)
# TraceMind

**TraceMind** – A lightweight, event-sourced smart agent framework.
It records and reflects every transaction, supports pipeline-based field analysis, static flow export, and interactive summaries/diagnosis/plans.
Designed with a clean DDD structure, minimal dependencies, and safe container execution.

---

Agent Evolution Timeline
─────────────────────────────────────────────
(1) Client + Server        (2) Digital Twin         (3) Autonomous Agent
    ───────────────        ───────────────          ────────────────────
    • Proxy / Adapter      • Mirror of entity       • Observer
    • Sip, Websocket       • Present + feedback     • Executor
    • Hide protocol        • IoT, Telecom           • Collaborator
      complexity           • State visualization    • AI-driven autonomy
                           • Simulation / feedback  • Coordination in MAS

 Value: simplify access    Value: insight + control Value: autonomy + learning

---

## ✨ Features

* **Event Sourcing Core**: append-only event store powered by the Binary Segment Log (`tm/storage/binlog.py`). JSONL and SQLite remain optional adapters planned for future expansion.
* **DDD Structure**: clear separation of domain, application, and infrastructure layers.
* **Pipeline Engine**: field-driven processing (Plan → Rule → Step), statically analyzable.
* **Tracing & Reflection**: every step produces auditable spans.
* **Smart Layer**:

  * Summarize: human-readable summaries of recent events.
  * Diagnose: heuristic anomaly detection with suggested actions.
  * Plan: goal → steps → optional execution.
  * Reflect: postmortem reports and threshold recommendations.
* **Visualization**:

  * Static: export DOT/JSON diagrams of flows.
  * Dynamic: SSE dashboard with live DAG and insights panel.
* **Protocols**:

  * MCP (Model Context Protocol) integration (JSON-RPC 2.0) – see the
    [latest specification](https://modelcontextprotocol.io/specification/latest)
    and the [community GitHub org](https://github.com/modelcontextprotocol).
    Example flow recipe:
    ```python
    from tm.recipes.mcp_flows import mcp_tool_call

    spec = mcp_tool_call("files", "list", ["path"])
    runtime.register(_SpecFlow(spec))
    ```
* **Interfaces**:

  * REST API: `/api/commands/*`, `/api/query/*`, `/agent/chat`.
  * Metrics: `/metrics` (Prometheus format).
  * Health checks: `/healthz`, `/readyz`.

---

## 📂 Architecture (ASCII Overview)

```
                +----------------+
                |   REST / CLI   |
                +----------------+
                         |
                    [Commands]
                         v
                +----------------+
                |  App Service   |
                +----------------+
                         |
                  +------+------+
                  |             |
             [Event Store]   [Event Bus]
                  |             |
          +-------+        +----+-----------------+
          |                |                      |
     [Projections]   [Pipeline Engine]      [Smart Layer]
                          |              (Summarize/Diagnose/Plan/Reflect)
                          v
                      [Trace Store]
```

---

## 📚 Documentation

- [Flow & policy recipes](docs/recipes-v1.md)
- [Helpers reference](docs/helpers.md)
- [Policy lifecycle & MCP integration](docs/policy.md)

### Scale & Reliability

- [Scale & Reliability guide](docs/scale-and-reliability.md)
- [Queue retries & DLQ](docs/howto/retries_dlq.md)

### Safety & Governance

- [Governance overview](docs/governance.md)
- [Guardrails](docs/guard.md)
- [Human approvals](docs/hitl.md)

---

## 🚀 Quick Start

### Requirements

* Python 3.11+
* Standard library only (no third-party dependencies by default)

### Run in development

```bash
# clone
git clone https://github.com/<your-username>/trace-mind.git
cd trace-mind

# install and scaffold a demo project
pip install -e .

# verify CLI wiring
which python
which pip
which tm
tm --help
python -m tm --help

tm init demo
cd demo

# execute the sample flow
tm run flows/hello.yaml -i '{"name":"world"}'
```

> Tip: if `which tm` does not return a path, activate your virtual environment and rerun `pip install -e .` so the console script is added to your `PATH`.

### Run in container

```bash
docker build -t trace-mind ./docker

docker run --rm -it \
  --read-only \
  -v $(pwd)/data:/data \
  -p 8080:8080 \
  trace-mind
```


### Scale & Reliability demo

See the [Scale & Reliability guide](docs/scale-and-reliability.md) for full context. The commands below can be pasted into a shell to exercise the worker pool, queue stats, and DLQ tooling.

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

---

## 🧩 Roadmap

* [ ] More connectors (file bridge, http bridge, kafka bridge)
* [ ] Richer dashboard with interactive actions
* [ ] Adaptive thresholds in Reflector
* [ ] Optional LLM integration for natural summaries

---

## 📜 License

MIT (for personal and experimental use)

Quickstart:
tm init demo --template minimal
cd demo && tm run flows/hello.yaml -i '{"name":"world"}'
More details: docs/quickstart.md
