# TM-SPEC-RUNTIME-AGENT-V0

## Overview

`TM-SPEC-RUNTIME-AGENT-V0` defines how TraceMind composes runnable agents and bundles. Runtime agents are described by an `AgentSpec` that declares who is running, what runtime to invoke, what contract (IORefs/effects) governs inputs and outputs, and what evidence they emit. Agent bundles are artifacts (`agent_bundle`) that wire one or more AgentSpecs together into a plan that TraceMind can execute end-to-end.

## AgentSpec

Each agent must publish an `AgentSpec` before execution. The spec captures identity, runtime selection, contract obligations, configurable parameters, and the evidence it produces.

| Field | Description |
| --- | --- |
| `agent_id` (string) | Globally unique identifier, e.g., `tm-agent/runner:0.1`. |
| `name` (string) | Human-friendly label, used in logs and bundle plans. |
| `version` (semver) | Indicates the schema/runtime compatibility version. |
| `runtime` (object) | Describes the execution environment. Includes `kind` (e.g., `tm-shell`, `lambda`, `container`) and `config` (runtime-specific args such as image, interpreter path, or resource limits). |
| `contract` (object) | Mirrors `TM-SPEC-IO-CONTRACT-V0`. Lists `inputs` and `outputs` (IORefs) plus declared `effects`, linking runtime behavior to verifiable IO. |
| `config_schema` (string/object) | Schema (JSON Schema, protobuf, etc.) for agent-specific configuration. Agents must validate incoming config data before initialization. |
| `evidence_outputs` (list) | Named evidence streams (hashes, metrics, receipts). Each entry names the evidence, describes how it is collected, and maps to IORefs or metadata produced on completion. |

### Contract binding

AgentSpecs must reference IORefs defined by `TM-SPEC-IO-CONTRACT-V0`. Inputs used during initialization or runtime must be declared as `io_refs` the agent reads, while outputs and side-effects must appear in the `effects` declaration. Linkages between `config_schema` and `contract.schema` ensure type-safe provisioning.

## AgentBundle (artifact_type=`agent_bundle`)

An AgentBundle is serialized as a TraceMind artifact (`artifact_type: agent_bundle`) whose body names the agents, the execution plan, and metadata such as target environment and policy hints.

```yaml
artifact_type: "agent_bundle"
version: "v0"
body:
  bundle_id: "tm-bundle/xyz"
  agents:
    - agent_id: "tm-agent/runner:0.1"
      role: "initializer"
    - agent_id: "tm-agent/worker:0.1"
      role: "executor"
  plan:
    - step: "init"
      agent_id: "tm-agent/runner:0.1"
      inputs: ["artifact:config"]
    - step: "run"
      agent_id: "tm-agent/worker:0.1"
      inputs: ["state:workload"]
    - step: "emit"
      agent_id: "tm-agent/worker:0.1"
      outputs: ["artifact:result"]

```

Each plan step names the agent, the phase (`init`, `run`, `emit`, `finalize`), and the IORefs it touches. TraceMind executes the plan in order, binding data from previous steps. Bundles should document any prerequisites (e.g., required artifacts) in `meta.preconditions`.

## Lifecycle stages

1. **Init** – Agents hydrate configuration via `config_schema`, resolve `required` IORefs, and ensure `io_refs` marked `required` are present before proceeding.
2. **Run** – The runtime executes the agent logic. The agent honors its contract by producing declared effects and may signal rollback paths or evidence generation hooks.
3. **Emit evidence** – After success (or controlled rollback), the agent writes its `evidence_outputs` to the agreed IORefs or aggregate logs, preserving hashes/metrics needed for downstream verification.
4. **Finalize** – Agents release resources, mark `effects` as completed or failed, and optionally update bundle metadata (status, result artifact references). Non-idempotent steps should record nonces to prevent duplicate retries.

## TraceMind execution mapping

- **Agents → Runnables**: TraceMind resolves each `agent_id` to a runnable (container, script, plugin) defined by `runtime.kind` and provisions its `config_schema`.
- **Bundles → Plans**: The `plan` array orders lifecycle stages, ensuring init steps populate IORefs before dependent runs execute. Evidence steps appear where `evidence_outputs` are consumed downstream.
- **Verification**: After every plan step, TraceMind validates the IO contract (per `TM-SPEC-IO-CONTRACT-V0`) and records evidence statuses. AgentBundles therefore act both as deployment manifest and verifier input.

## Acceptance notes

This spec is intentionally minimal: it outlines the schema fields and lifecycle to enable TraceMind’s plan execution while leaving room for future extensions (e.g., multi-agent parallelism, more granular evidence descriptors).
