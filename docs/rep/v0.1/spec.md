# TraceMind Runtime Execution Protocol (REP) v0.1

## 1. Overview

The Runtime Execution Protocol (REP) defines the JSON-RPC interactions between the TraceMind orchestrator (Python) and external runtimes (`ProcessEngine`). REP v0.1 covers milestone M0 and formalizes the stdio transport, method contracts, and error taxonomy used to execute flows compiled to the Flow IR v1.0.0.

## 2. Terminology and Project Model

- **Orchestrator**: The TraceMind Python process invoking an engine.
- **Runtime**: External process that implements REP methods and executes steps.
- **Run**: A single execution of a compiled flow.
- **Event**: Structured payload emitted by the runtime to describe progress or logs.
- **Project runtime**: The single runtime implementation configured during `tm init`.

Each TraceMind project binds to exactly one runtime family at initialization time. The selection determines both the REP executor binary and the plugin toolchain (e.g. C runtime pairs with C plugins, Rust runtime with Rust plugins). Subsequent CLI invocations default to this runtime; overrides are supported only for development diagnostics. Tooling must surface a clear warning if the configured runtime and plugin set do not share the same language family.

## 3. Transport

- Transport: JSON-RPC 2.0 messages over UTF-8 encoded stdin/stdout.
- One runtime process is spawned per run in M0. TCP or multiplexed sessions are out of scope.
- The orchestrator launches the runtime with the IR payload supplied via `Runtime.StartRun`.
- Communication MUST be synchronous request/response pairs; runtimes may send notifications only where noted.

### 3.1 Process Lifecycle

1. Orchestrator spawns runtime executable with environment variables described in Section 8.
2. Once stdio streams are established, the orchestrator issues `Runtime.Capabilities`.
3. If capabilities are acceptable, orchestration continues with `Runtime.StartRun`.
4. Orchestrator calls `Runtime.Poll` until completion or timeout.
5. On cancellation, orchestrator issues `Runtime.Cancel` and terminates the process if it fails to exit gracefully.

The orchestrator enforces an overall engine timeout (default 120 seconds). Hitting this timeout maps to CLI exit code `4`.

## 4. JSON-RPC Envelope Requirements

- Each request must conform to [JSON-RPC 2.0](https://www.jsonrpc.org/specification).
- Method names use the `Runtime.*` namespace.
- The orchestrator assigns monotonically increasing numeric `id` values starting at 1.
- Runtimes must echo the same `id` in responses.
- Notifications (requests without `id`) are not used in v0.1.
- All responses must be single JSON objects terminated by newline.

Invalid JSON, protocol mismatches, or unexpected EOF result in a `RuntimeInternal` error (code `3001`).

## 5. Method Reference

### 5.1 `Runtime.Capabilities`

- **Request params**

```json
{}
```

- **Response result**

```json
{
  "version": "0.1.0",
  "step_kinds": ["http.get", "mcp.call"],
  "limits": {
    "concurrency": 4
  }
}
```

Fields:

| Field           | Type    | Required | Notes                                                   |
| --------------- | ------- | -------- | ------------------------------------------------------- |
| `version`       | string  | yes      | Runtime implementation version (`semver`).              |
| `step_kinds`    | array   | yes      | Set of step types supported by the runtime.             |
| `limits`        | object  | yes      | Resource hints; currently only `concurrency` is defined.|

Missing required fields or incompatible `step_kinds` cause the orchestrator to abort with exit code `3`.

### 5.2 `Runtime.StartRun`

- **Request params**

```json
{
  "ir": { /* Flow IR v1.0.0 object */ },
  "inputs": { /* user inputs, may be empty */ },
  "options": {
    "run_id": "uuid",
    "trace_id": "uuid",
    "allow_shell": false
  }
}
```

- **Response result**

```json
{
  "run_id": "uuid"
}
```

The runtime must validate the IR version before executing. Unsupported versions must produce a `Validation` error (`code` 1001).

### 5.3 `Runtime.Poll`

- **Request params**

```json
{
  "run_id": "uuid"
}
```

- **Response result**

```json
{
  "status": "running",
  "events": [
    {
      "type": "log",
      "timestamp": "2024-06-30T18:25:43.511Z",
      "level": "info",
      "message": "step started",
      "step_id": "http_1"
    }
  ],
  "summary": {
    "completed_steps": 2,
    "failed_steps": 0
  }
}
```

Status values:

| Value       | Meaning                         |
| ----------- | -------------------------------- |
| `pending`   | Run accepted but not started.    |
| `running`   | In-flight execution.             |
| `completed` | Run finished successfully.       |
| `failed`    | Run aborted due to error.        |

Events array is optional; when present, each element must be a JSON object with a `type` field. M0 recognizes `log` and `step` types but consumers must ignore unknown event types.

### 5.4 `Runtime.Cancel`

- **Request params**

```json
{
  "run_id": "uuid"
}
```

- **Response result**

```json
{
  "ok": true
}
```

Runtimes should attempt best-effort cancellation. If the run already completed, returning `ok: true` is acceptable.

### 5.5 `Runtime.Health`

- Optional heartbeat invoked when the orchestrator decides to reuse sessions (future). Implementations should return:

```json
{
  "ok": true,
  "details": {}
}
```

For M0 the method MAY be unimplemented; the runtime can return `Method not found` and the orchestrator will ignore it.

## 6. Error Taxonomy

Errors are returned using the JSON-RPC `error` object:

```json
{
  "code": 1001,
  "message": "Unsupported IR version",
  "data": {
    "step_id": "http_1",
    "attempt": 0,
    "retriable": false,
    "details": {
      "expected": "1.0.0",
      "received": "2.0.0"
    }
  }
}
```

Error classes:

| Code range | Name              | Default `retriable` | Description                                         |
| ---------- | ----------------- | ------------------- | --------------------------------------------------- |
| 1000-1999  | `Validation`      | false               | IR incompatibility, malformed inputs, unsupported step kinds. |
| 2000-2999  | `StepFailure`     | per IR retry policy | Downstream or business logic failures.              |
| 3000-3999  | `RuntimeInternal` | false               | Transport failures, crashes, timeouts, unexpected exceptions. |

Specific codes defined in v0.1:

| Code  | Description                        |
| ----- | ---------------------------------- |
| 1001  | Unsupported IR version             |
| 1002  | Unsupported step kind              |
| 1003  | Invalid IR payload (schema)        |
| 2001  | Step execution failed              |
| 3001  | Broken transport / EOF / invalid JSON |
| 3002  | Runtime panicked / unhandled error |

The orchestrator maps error classes to CLI exit codes:

| Error class       | CLI exit code |
| ----------------- | ------------- |
| Validation        | 3             |
| StepFailure       | 1 (unless overridden by retry policy) |
| RuntimeInternal   | 4             |

## 7. Logging and Events

- Runtimes should emit structured events through `Runtime.Poll` results.
- Each event must include `timestamp` (RFC 3339) and `type`.
- For `log` events include `level`, `message`, optional `step_id`.
- For `step` events include `step_id`, `state` (`started`, `succeeded`, `failed`), and optional metrics.
- Events are appended to orchestrator logs and may be persisted in future milestones.

## 8. Environment and Configuration

The orchestrator sets the following environment variables when launching the runtime:

| Variable                    | Description                                          |
| --------------------------- | ---------------------------------------------------- |
| `TRACE_MIND_RUN_ID`        | Run identifier (matches `options.run_id`).            |
| `TRACE_MIND_TRACE_ID`      | Trace identifier for correlation.                     |
| `TRACE_MIND_ENGINE_TIMEOUT`| Seconds before orchestrator terminates the process.   |
| `TRACE_MIND_ALLOW_SHELL`   | `"0"` or `"1"` reflecting policy configuration.       |
| `TRACE_MIND_LOG_JSON`      | `"1"` if structured stdout logging is expected.       |

Authentication tokens are not used in M0; future milestones will add `TRACE_MIND_BEARER_TOKEN`.

Runtime discovery information lives in `tm/config/runtime.yaml`. The file stores the single project runtime identifier (selected during `tm init`) along with metadata such as language family and executor path. CLI commands resolve `ProcessEngine` executables from this config unless an explicit override flag is supplied.

## 9. Capability Negotiation

1. Orchestrator issues `Runtime.Capabilities`.
2. Compare `step_kinds` against required set derived from IR manifest.
3. On mismatch, orchestrator exits with code `3` and caches the runtime capabilities at `~/.trace_mind/runtime_capabilities/<engine>.json`.
4. Users may clear caches via `tm runtime cache clear --engine <name>`.

As part of this negotiation the orchestrator also verifies that the runtime language family aligns with the project’s plugin bundle (e.g. Rust runtime + Rust plugins). A mismatch is treated as a validation error and should be surfaced with guidance to re-run `tm init` with the desired runtime.

## 10. Cancellation and Timeouts

- Orchestrator enforces per-run timeout. Exceeding results in `RuntimeInternal` error (`3001`) with `cause: "Timeout"`.
- Step-level timeouts are enforced by the runtime according to IR hints.
- On user cancellation, orchestrator sends `Runtime.Cancel` once and waits up to 5 seconds before force terminating the process.

## 11. Testing Requirements

- Contract tests under `tests/contract_proc/` must cover:
  - Capability handshake (happy path and mismatch).
  - Start/Run/Poll lifecycle including completion and failure.
  - Transport breakage mapping to `3001`.
  - Orchestrator handling of validation exit code `2` when IR schema fails before REP handshake.
  - Engine timeout -> exit code `4`.

## 12. Future Extensions (Out of Scope for v0.1)

- Long-lived runtime sessions with heartbeat monitoring (`Runtime.Health`).
- Binary payload streaming and large artifact transfer.
- Authenticated transports (Bearer token, mTLS) and remote TCP execution.
- Rich observability metrics and state streaming.

Changes introducing the features above will either be additive within REP v0.x or require a new major version, as documented in the compatibility matrix.
