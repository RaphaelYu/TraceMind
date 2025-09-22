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

* **Event Sourcing Core**: append-only event store (SQLite / JSONL).
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

## 🚀 Quick Start

### Requirements

* Python 3.11+
* Standard library only (no third-party dependencies by default)

### Run in development

```bash
# clone
 git clone https://github.com/<your-username>/trace-mind.git
 cd trace-mind

# run minimal server
 python -m agent.cli run --bind 0.0.0.0:8080 --data /tmp/trace-mind

# test a command
 curl -X POST http://localhost:8080/api/commands/upsert \
   -H "Content-Type: application/json" \
   -d '{"kind":"NFProfile","obj_id":"nf-1","payload":{"status":"ALIVE"}}'

# get summary via chat endpoint
 curl -X POST http://localhost:8080/agent/chat \
   -H "Content-Type: application/json" \
   -d '{"text":"summarize last 10 minutes"}'
```

### Run in container

```bash
docker build -t trace-mind ./docker

docker run --rm -it \
  --read-only \
  -v $(pwd)/data:/data \
  -p 8080:8080 \
  trace-mind
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
