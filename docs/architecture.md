# achtecture of the system

1. ServiceBody binds a domain model (ModelSpec) with operations (BindingSpec) and routes requests via the OperationRouter.

2. FlowRuntime acts as a lightweight Event Bus: it receives events (ctx), selects the right FlowSpec, and executes steps sequentially.

3. CorrelationHub manages deferred results (DEFERRED), linking pending requests with their final outcomes by correlation ID.

4. Trace & Recorder capture replayable FlowTraces and update metrics (binlog, Prometheus exposition, or file exporters).

5. Retrospect allows replay and windowed aggregation from historical files/binlogs for local backtracking and audits.

6. External connectors (HTTP, K8s, Docker, MCP) are just event sources; recipes generate FlowSpecs to integrate them.

                          ┌────────────────────────────────────────┐
                          │              External IO               │
                          │  HTTP API   K8s API   Docker API  MCP  │
                          └───────────────┬──────────┬─────────────┘
                                          │          │
                                   (events/requests: op + payload)
                                          │
                             ┌────────────▼────────────┐
                             │        ServiceBody       │
                             │  - ModelSpec (entity)    │
                             │  - BindingSpec (rules)   │
                             │  - OperationRouter       │
                             └────────────┬────────────┘
                                          │  route(ctx)
                                    ctx = {model, op, payload, ...}
                                          │
                          ┌───────────────▼────────────────┐
                          │          FlowRuntime            │
                          │   (acts like a light Event Bus) │
                          │  - select Flow/FlowSpec         │
                          │  - dispatch step-by-step        │
                          │  - ResponseMode: IMMEDIATE/DEF. │
                          └───────┬───────────────┬─────────┘
                                  │               │
                       (deferred) │               │ (step results / final)
                                  │               │
                     ┌────────────▼──────┐   ┌────▼────────────────────┐
                     │  CorrelationHub   │   │      Trace & Metrics     │
                     │  req_id ↔ result  │   │                          │
                     └─────────┬─────────┘   │  FlowTrace  PipelineTrace│
                               │             │  Recorder(Obs)           │
                        signal │             │  ┌───────────┬────────┐  │
                               │             │  │ Binlog    │ Prom   │  │
                          ┌────▼──────┐      │  │ (replay)  │ /metrics│  │
                          │ Deferred  │      │  │           │ (text)  │  │
                          │ Responses │      │  └───────────┴────────┘  │
                          └───────────┘      └────────────┬─────────────┘
                                                          │
                                                  ┌───────▼────────┐
                                                  │   Retrospect   │
                                                  │  (file/binlog  │
                                                  │   window agg)  │
                                                  └────────────────┘
