# TM-SPEC-CONTROLLER-BUNDLE-V0

## Overview
`TM-SPEC-CONTROLLER-BUNDLE-V0` defines how TraceMind represents an Observe→Decide→Act controller loop as an artifact bundle. The spec introduces three artifacts (`EnvSnapshot@v0`, `ProposedChangePlan@v0`, `ExecutionReport@v0`) plus the accompanying runtime agents (`ObserveAgent`, `DecideAgent`, `ActAgent`) so planners and verifiers can trust the deterministic stages of observation, reasoning, and execution.

### Lifecycle
1. **Observe** — `EnvSnapshot` captures current state and context for the controller loop.
2. **Decide** — `ProposedChangePlan` carries the candidate plan originated by the LLM-enabled decision step plus metadata needed for policy/idempotency checks.
3. **Act** — `ExecutionReport` records what was executed, compliance with policy guard decisions, and evidence linking effects to their declared IORefs.

## Artifact Bodies

### EnvSnapshot@v0
- **Purpose**: Immutable snapshot of the observed environment that seeds every controller iteration.
- **Envelope schema**: `artifact_type: environment_snapshot`, `version: v0`, `meta.phase: "derived"`.
- **Body schema**:
  - `snapshot_id` (string, required): deterministic id (e.g., hash) for deduplication.
  - `timestamp` (string, RFC3339): observation timestamp.
  - `environment` (object): sensor/state data (fields depend on controller domain).
  - `constraints` (list of objects): static guard conditions relevant to the loop (optional).
  - `data_hash` (string): hash of `environment` + `constraints` for deterministic verification.
- **Determinism**: The snapshot must be replayable; observers cannot embed entropy. `snapshot_id` and `data_hash` feed into the idempotency key used by downstream agents.

### ProposedChangePlan@v0
- **Purpose**: Contains the plan produced by the Decide stage. Verifiers use this to check whether requested effects obey policy before execution.
- **Body schema**:
  - `plan_id` (string, required) — derived from input snapshot hash + intent.
  - `intent_id` (string) — reference to controlling intent.
  - `decisions` (array of objects):
    - `effect_ref` (string) — IORef targeted.
    - `target_state` (object) — finalized payload intended for the effect.
    - `idempotency_key` (string) — computed via `snapshot_id` + `effect_ref`.
    - `reasoning_trace` (string, optional) — link to evidence (`DecideAgent` output).
  - `llm_metadata` (object):
    - `model` (string)
    - `prompt_hash` (string)
    - `determinism_hint` (enum: `deterministic`, `replayable`, `heuristic`)
  - `summary` (string) — human-readable description of the plan.
  - `policy_requirements` (collection) — sets of resource targets that must be allowlisted before `ActAgent` runs.
- **Verification**: The planner must compute `plan_id` deterministically from `snapshot_id` and `decisions`. The `idempotency_key` for each effect combines `plan_id` + `effect_ref`.
- **LLM constraints**: While the Decide stage may internally use an LLM, the resulting plan must be replayable without re-invoking the LLM. All evidence (model hash, prompt hash, reasoning trace) must be stored in `llm_metadata` or `decisions`.

### ExecutionReport@v0
- **Purpose**: Describes the outcomes observed after the `ActAgent` applies the proposed plan.
- **Body schema**:
  - `report_id` (string) — same value as `plan_id` for correlation.
  - `artifact_refs` (object) — map of IORefs written during execution to their resolved values.
  - `status` (string, enum: `succeeded`, `partial`, `failed`).
  - `policy_decisions` (array): each entry records `effect_ref`, `allowed` (bool), `reason`.
  - `errors` (array of strings, optional) — runtime exceptions or denials.
  - `artifacts` (object) — evidence produced by each agent (`ObserveAgent` snapshot hash, `DecideAgent` reasoning, `ActAgent` command logs).
  - `execution_hash` (string) — hash of `artifact_refs`, `policy_decisions`, and `status`.
- **Determinism**: `execution_hash` + `artifact_refs` combine to provide auditors with the final state necessary for future snapshots.

## Runtime Agents

### ObserveAgent
- **IO contract**:
  - Inputs: none (bootstrap context provided via `EnvSnapshot` preconditions).
  - Outputs: `state:env.snapshot`.
  - Effects:
    - `capture_snapshot` → `state:env.snapshot` (resource effect, `idempotency.key_fields: ["snapshot_id"]`).
- **Behavior**: Reads sensors, normalizes data, writes snapshot w/ `snapshot_id` and `data_hash`.
- **Evidence**: Emits `builtin.observer.snapshot` containing raw sensor payload + computed hash.

### DecideAgent (LLM)
- **IO contract**:
  - Inputs: `state:env.snapshot`.
  - Outputs: `artifact:proposed.plan`.
  - Effects:
    - `plan_decision` → `artifact:proposed.plan` (resource effect, `idempotency.key_fields: ["plan_id"]`).
- **Constraints**:
  - Must use input `snapshot_id` when deriving `plan_id`.
  - Must embed `llm_metadata` and ensure replayability (no runtime randomness post-plan generation).
  - Must declare required policy allowlist targets before producing the plan.
- **Evidence**: Records `builtin.decide.plan` with `model`, `prompt_hash`, and `decisions`.

### ActAgent
- **IO contract**:
  - Inputs: `artifact:proposed.plan`.
  - Outputs: `artifact:execution.report`, `state:act.result`.
  - Effects: one per targeted resource from the plan, each `resource` effect must include `idempotency.key_fields` referencing the plan’s `idempotency_key`.
- **Policy enforcement**: Evaluates `policy_requirements` from the plan via `PolicyGuard` before executing each effect. Denial aborts execution and records `policy_decisions` in the report.
- **Evidence**: Captures stdout/stderr, target responses, and final status under `builtin.act.report`.

## Example agent bundle mapping

```yaml
body:
  agents:
    - agent_id: tm-agent/observer:0.1  # ObserveAgent
    - agent_id: tm-agent/decide:0.1    # DecideAgent
    - agent_id: tm-agent/actor:0.1     # ActAgent
  plan:
    - step: observe
      agent_id: tm-agent/observer:0.1
      outputs: ["state:env.snapshot"]
    - step: decide
      agent_id: tm-agent/decide:0.1
      inputs: ["state:env.snapshot"]
      outputs: ["artifact:proposed.plan"]
    - step: act
      agent_id: tm-agent/actor:0.1
      inputs: ["artifact:proposed.plan"]
      outputs: ["artifact:execution.report"]
      meta:
        policy:
          allow:
            - state:env.snapshot
            - artifact:proposed.plan
            - artifact:execution.report
```

## Policy points and idempotency
- **ObserveAgent** effects tie to `state:env.snapshot`; policy guard allowlist must include this resource before running.
- **DecideAgent** notarizes `artifact:proposed.plan` and publishes `policy_requirements` that `ActAgent` uses for guard evaluation.
- **ActAgent** enforces guards per effect target, records `policy_decision` evidence when permitted/denied, and writes `execution_report` that includes the denial reason when an effect is blocked.
- **Idempotency keys**: Observers use `snapshot_id`; Decide/Act use `plan_id` plus the referenced IORef or decision identifier to guarantee deterministic reruns.

## Replay rules
- **No LLM replays**: Once the plan is emitted, re-executions must reuse `artifact:proposed.plan`; `DecideAgent` may not rerun the LLM unless the snapshot changes.
- **Report-driven control**: Execution reports feed back into the next snapshot, enabling safe loops (report becomes part of future `EnvSnapshot` metadata).

## Evidence and auditing
- Every agent must call `self.add_evidence(kind, payload)` with structured payloads (`builtin.observer.snapshot`, `builtin.decide.plan`, `builtin.act.report`) for the executor to append to `ExecutionContext.evidence`.
- `ExecutionReport.policy_decisions` aggregates guard decisions so reviewers can inspect why effects executed or failed.

