# TM-SPEC-IO-CONTRACT-V0

## Overview

`TM-SPEC-IO-CONTRACT-V0` formalizes how runtime agents declare the inputs and outputs they consume or mutate. The v0 contract stays intentionally minimal: it introduces IO references (IORefs) and a paired effect declaration model, plus a small set of verifier-friendly static checks so that lint tools can confirm closure, typing, and idempotency without running the agent.

## IORef structure

Each IORef describes a logical I/O endpoint or resource the agent interacts with. Agents must list every IORef they touch in `io_refs` before any effect declaration references it.

| Field | Description |
| --- | --- |
| `ref` (string) | Unique identifier (e.g., `artifact:config`, `state:user`). |
| `kind` (enum) | One of `artifact`, `resource`, `service`, or `environment`; indicates the domain semantics and default trust level. |
| `schema` (string/object) | Path or inline schema (JSON Schema, protobuf descriptor, etc.) describing the payload that flows through this ref. |
| `required` (boolean) | If `true`, the agent must attest that the ref is populated before effects that depend on it run. |
| `mode` (enum) | `read`, `write`, or `mutate` (can be combined via arrays in future revisions). Determines directionality and whether idempotency keys are mandatory. |

IORefs are interpreted as a closure of all declared resources; any resource not present in `io_refs` must not be targeted by effects in this contract.

## Effect declaration structure

`effects` map the committed IORefs to declarative side-effects. Each effect must name its target and explain how it can be verified or rolled back.

| Field | Description |
| --- | --- |
| `name` (string) | Human-readable identifier for the effect. |
| `kind` (string) | Always `resource` in v0, asserting the effect occurs on an IORef-defined resource. |
| `target` (string) | The `ref` of the IORef this effect mutates or observes. |
| `idempotency` (object) | Describes whether the effect is idempotent. Include `type` (options: `keyed`, `reentrant`, `non-idempotent`), and if `keyed`, list `key_fields` (paths inside the request payload). |
| `rollback` (string, optional) | Reference to another `effects` entry (or a standard rollback descriptor) that can undo or safely negate this effect. |
| `evidence` (object) | Specifies how to prove the effect completed. V0 allows `type` (`hash`, `status`, `range`) plus `path` or `metric` references; concrete checkers must annotate how to read the evidence. |

## Static checks (lint/verifier rules)

1. **IO closure**: Every `target` or `rollback` reference must point to an IORef listed in `io_refs`. Missing IORefs are a fatal lint error.
2. **Type/schema consistency**: The data flowing through an effect must align with the declared IORef `schema`. Validators must compare annotated payload shapes or metadata tags against the schema before allowing the effect to execute.
3. **Effect explicitness**: Agents must declare at least one effect for each IORef they write or mutate. Read-only IORefs may remain effect-free if the agent only consumes data.
4. **Idempotency key availability**: For `mode` values that include `write` or `mutate`, `effects.idempotency.type` must not be `undefined`. For `keyed` idempotent effects, the referenced `key_fields` must exist in the request schema, ensuring callers can reissue requests safely.
5. **Evidence pairing**: Every effect must supply `evidence` so verifiers can confirm success or retry. Missing evidence should trigger a warning that the effect cannot be audited by default.

## Example contract

```yaml
io_refs:
  - ref: "artifact:config"
    kind: "artifact"
    schema: "schemas/config-schema.json"
    required: true
    mode: "read"
  - ref: "state:workload"
    kind: "resource"
    schema:
      type: object
      properties:
        workload_id:
          type: string
        status:
          enum: [pending, running, succeeded, failed]
    required: false
    mode: "mutate"

effects:
  - name: "configure-workload"
    kind: "resource"
    target: "artifact:config"
    idempotency:
      type: "keyed"
      key_fields: ["artifact_id"]
    evidence:
      type: "hash"
      path: "/state/config.hash"
  - name: "update-status"
    kind: "resource"
    target: "state:workload"
    idempotency:
      type: "reentrant"
    rollback: "reset-status"
    evidence:
      type: "status"
      metric: "workload_state"
  - name: "reset-status"
    kind: "resource"
    target: "state:workload"
    idempotency:
      type: "non-idempotent"
    evidence:
      type: "status"
      metric: "workload_state"
```

## Verifier guidance

- **Collect IORefs**: Build a symbol table mapping `ref` → schema/mode. Reject any effect that references unknown refs or mismatched modes.
- **Validate static checks**: Run the five rules above before execution and reject the contract if any fail.
- **Evidence resolution**: For each effect, ensure the evidence descriptor points to a retrievable log, metric, or hash source. Missing or unresolvable evidence should flip the effect into `pending verification`.
- **Idempotency enforcement**: If an effect is declared `non-idempotent`, require the caller to supply a deterministic nonce or document why retries are unsafe.
