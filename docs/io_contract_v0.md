# IO Contract v0

TraceMind runtime agents expose an explicit IO contract that spells out the data they consume (`inputs`), the data they produce (`outputs`), and the side effects they declare (`effects`). The CLI verifier (`tm artifacts verify`) and the lint suite (`tm.lint.io_contract_lint`) rely on this contract to confirm safety before any bundle runs.

## IORef structure

Each IORef binds a logical `ref` to metadata that the runtime can check statically and at runtime:

| Field | Description |
| --- | --- |
| `ref` | A unique identifier such as `artifact:config` or `state:result`. Agents use these labels when reading from or writing to the execution context (`ExecutionContext.get_ref` / `set_ref`). |
| `kind` | One of `artifact`, `resource`, `service`, or `environment`. This classification signals trust levels and evidence expectations. |
| `schema` | JSON Schema (or a named schema reference) describing the payload. Identical IO refs must share the same schema across the bundle. |
| `required` | If `true`, the agent must assert the ref exists before effects run. Required IORefs can drive plan preconditions. |
| `mode` | `read`, `write`, or `mutate`. Modes determine whether an IORef needs an effect declaration and how idempotency keys behave. |

IORefs declare the set of permissible data flows. Any effect that references an undeclared `ref` or an output step that writes to an unexpected ref will be flagged by the verifier (`EFFECT_TARGET`, `IO_BINDING`, `IO_CLOSURE` errors).

## Effects and governance

Each effect entry documents a resource mutation, its idempotency contract, and the evidence that proves completion:

```yaml
effects:
  - name: "update-state"
    kind: "resource"
    target: "state:workload"
    idempotency:
      type: "keyed"
      key_fields: ["artifact_id"]
    evidence:
      type: "hash"
      path: "/state/workload.hash"
```

- `target` must match an IORef defined in the same agent contract. The policy guard (`tm.policy.guard.PolicyGuard`) uses this target to decide whether the resource effect is allowlisted (`meta.policy.allow`) before permitting execution.
- `idempotency` records whether the effect can be replayed safely. For `keyed` effects, the verifier ensures the listed `key_fields` exist in the input payload so runs can be cached deterministically (`ExecutionContext.run_idempotent`).
- `evidence` explains how auditors confirm the effect. It feeds into `ExecutionContext.evidence` records so run reports can display hashes, statuses, or custom metrics.

Writers of IORefs with `mode: write` or `mode: mutate` must declare a corresponding effect (lint rule `EFFECT_REQUIRED`). Reads do not require effects but must be listed so steps declare `inputs` that exist (`IO_BINDING`). Every effect adds a `policy_guard` evidence record describing whether a target was allowed or denied.

## Idempotency, caching, and determinism

- `tm.runtime.context.ExecutionContext` maintains an idempotency cache so repeated plan steps reuse previous outputs. Effects with `key_fields` drive the cache key, while agents such as `tm-agent/noop:0.1` or `tm-agent/http-mock:0.1` register deterministic evidence to prove outputs.
- When an effect is declared `non-idempotent`, the runtime still records the action but expects callers to avoid retries unless an explicit nonce or guard is provided.

## Minimal example

An agent writing a mocked HTTP response might declare:

```yaml
inputs:
  - ref: artifact:http_request
    kind: artifact
    schema:
      type: object
    required: true
    mode: read
outputs:
  - ref: artifact:http_response
    kind: artifact
    schema:
      type: object
    required: false
    mode: write
effects:
  - name: "mock-response"
    kind: resource
    target: artifact:http_response
    idempotency:
      type: keyed
      key_fields: ["artifact_id"]
    evidence:
      type: status
```

This contract is part of the golden bundle at `specs/examples/agent_bundle_v0/agent_bundle_demo.yaml`, and the trace from `tm run bundle` captures the `artifact:http_response` payload plus the policy guard decision over `state:shell.stdout`.

## Commands that exercise IO contracts

- `tm artifacts verify <bundle.yaml>` checks IORefs, effects, and plan wiring. If the command exits successfully, the verifier writes deterministic metadata (`body_hash`, `meta.determinism`) into the bundle envelope, which downstream tools rely on.
- `tm artifacts accept <bundle.yaml> --out <dir>` saves the accepted artifact (with computed body hash) and can register it in a registry for reuse.
- `tm run bundle <accepted.yaml> --inputs artifact:foo='{"value":1}' --report run-report.yaml` executes the plan, enforces policy guard decisions, and records every IO ref transition in the report.

Together, these commands link the IO contract, verification, and runtime execution into a reproducible product workflow.
