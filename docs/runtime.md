# Runtime Execution Modes

TraceMind now supports **engine‑pluggable execution** for flows that have been compiled to
Flow IR. This document explains the runtime abstractions, configuration, and tooling delivered
in Milestone M0 so that new language runtimes (Rust, C++, RTOS targets, etc.) can be tested while
keeping the existing Python behaviour unchanged.

## 1. Engine Model

| Engine          | Description                                                                                |
| --------------- | ------------------------------------------------------------------------------------------ |
| `PythonEngine`  | Wraps the existing in-process execution hooks (`tm.dsl.runtime.call/switch/emit_outputs`). |
| `ProcessEngine` | Launches an external executor speaking REP v0.1 over stdio (JSON-RPC 2.0).                 |

Engines are configured globally and are **opt-in**. Existing commands (`tm run`, daemon
workers, etc.) continue to use the Python engine. Use the IR runner tooling described below for
runtime-agnostic smoke tests.

## 2. Runtime Configuration

Runtime discovery lives in `tm/config/runtime.yaml` (installed with the package). Projects can
override the path via `tm --runtime-config=<file>`.

```yaml
runtime:
  engine: python            # python | proc
  language: python          # language family
  plugins_language: python  # must match language for safety
  executor_path: null       # required when engine=proc
```

The CLI allows temporary overrides without editing the file:

```bash
tm --engine proc --executor-path tm/executors/mock_process_engine.py ...
```

## 3. Flow IR & Manifest

Compile flows with IR artifacts enabled:

```bash
tm dsl compile flows/ --emit-ir --out out/dsl
```

- `out/dsl/flows/<flow>.ir.json` – Flow IR v1.0.0 (schema in `docs/ir/v0.1/schema.json`).
- `out/dsl/manifest.json` – References every flow emitted this run.

Both files include metadata (`generated_at`, source path hashes) for traceability.

## 4. IR Runner (Runtime Smoke Tests)

Use the new IR runner to execute flows with the configured engine:

```bash
# Python engine (default)
tm runtime run --manifest out/dsl/manifest.json --flow flows.hello

# Process engine via JSON-RPC executor
tm --engine proc \
   --executor-path tm/executors/mock_process_engine.py \
   runtime run --manifest out/dsl/manifest.json --flow flows.hello
```

Programmatic access is available via `tm.runtime.run_ir_flow(flow_name, manifest_path, inputs={})`
which returns a `RunResult(status, state, events, summary)`.

### Online Verification CLI

`tm verify online` bundles the compilation (optional) and execution steps into a single command:

```bash
# Recompile sources before verification
tm verify online --flow flows.hello --sources flows/ policies/ --out out/dsl

# Use an existing manifest (defaults to out/dsl/manifest.json)
tm verify online --flow flows.hello

# Pass custom inputs and run via ProcessEngine
tm --engine proc --executor-path tm/executors/mock_process_engine.py \
  verify online --flow flows.hello --inputs '{"temperature": 72}'
```

The command prints a JSON summary (`flow`, `status`, `summary`, `events`) and exits non-zero when
the run fails.

## 5. Mock Executor & REP Contract

The mock executor (`tm/executors/mock_process_engine.py`) implements REP v0.1 and is used to
validate ProcessEngine integration.

- Capabilities: emits `opcua.read`, `opcua.write`, `policy.apply`, `dsl.emit`.
- Methods: `Runtime.Capabilities`, `Runtime.StartRun`, `Runtime.Poll`, `Runtime.Cancel`.
- Errors: `3001` (transport), `3002` (internal) mapped to CLI exit code `4`.

Contract tests live in `tests/contract_proc/test_process_engine_contract.py`.

## 6. Extending With New Runtimes

To add a new runtime (e.g. Rust or RTOS target):

1. Implement the REP v0.1 protocol in your executor (JSON-RPC over stdio/TCP-to-stdio proxy).
2. Advertise capabilities (`step_kinds`, concurrency limits) during `Runtime.Capabilities`.
3. Accept Flow IR v1.0.0 payloads and honour node `type`, `with`, `timeout_ms`, `retry`.
4. Return structured events/logs via `Runtime.Poll`.
5. Package the executor binary and point `runtime.executor_path` at it.
6. Use `tm runtime run ...` together with project-specific test inputs for smoke verification.

The ProcessEngine will validate capabilities and surface incompatible flows before execution
(`CapabilitiesMismatch`).

## 7. Status & Next Steps

- Python remains the authoritative runtime for `tm run`, daemon workers, and policy verification.
- IR runner + mock executor allow “what-you-see-is-what-you-get” testing across engines.
- Future milestones can introduce additional transports (TCP, containers) without breaking the
IR tooling or CLI ergonomics delivered in M0.
