# TraceMind Flow IR v0.1 Specification

## 1. Purpose and Scope

This document defines the canonical intermediate representation (IR) produced by `trace-mind dsl compile --emit-ir` in milestone M0. The IR captures all information a remote runtime requires to execute a flow without direct access to TraceMind policy code. The schema described here is normative for `version: "1.0.0"` and applies to all flow types (WDL/SDL/PDL) compiled by the TraceMind DSL toolchain.

## 2. Versioning Policy

- The IR carries a semantic version string at `$.version`.
- All `1.y.z` releases must remain backward compatible with consumers that support `1.0.0`. Additive fields/enum values are permitted; structural changes are not.
- Breaking changes require incrementing the major version (e.g. `2.0.0`) and explicit runtime opt-in. Older runtimes must reject newer major versions with a validation error.
- The schema revision history lives beside this spec at `docs/ir/v0.1/schema.json`. Migration fixtures ensure previously emitted IRs remain loadable.

## 3. File Layout

| Artifact                                   | Description                                                      |
| ------------------------------------------ | ---------------------------------------------------------------- |
| `out/dsl/flows/<flow_name>.ir.json`        | Per-flow IR document conforming to the schema herein.            |
| `out/dsl/manifest.json`                    | Atomic list of flows emitted in the current compile invocation.  |
| `out/dsl/.ir-cache/` (implementation detail) | Optional build cache; not part of the public contract.           |

`dsl compile --clean` removes the IR files and manifest only. `--clean-all` is required to wipe the entire `out/dsl` directory.

## 4. Top-Level Structure

Each IR document is a canonical JSON object shaped as follows (schematic, non-normative values):

```json
{
  "version": "1.0.0",
  "flow": {
    "name": "plant.monitor",
    "timeout_ms": 600000
  },
  "constants": {
    "policyRef": "maint.default",
    "policy": { "...": "baked policy payload" }
  },
  "inputs_schema": {},
  "graph": {
    "nodes": [],
    "edges": []
  },
  "metadata": {
    "generated_at": "2024-06-30T18:25:43.511Z",
    "source_file": "examples/dsl/opcua/flows/plant-monitor.wdl.yaml"
  }
}
```

All properties are mandatory unless marked optional in Section 5.

## 5. Field Semantics

### 5.1 `version`

- Type: string, semantic version (`major.minor.patch`).
- Must match the schema version supported by the runtime. For M0 this is `"1.0.0"`.

### 5.2 `flow`

| Field        | Type    | Required | Notes                                              |
| ------------ | ------- | -------- | -------------------------------------------------- |
| `name`       | string  | yes      | Normalized flow name (slug).                       |
| `timeout_ms` | integer | yes      | Maximum runtime duration for the flow (>= 0).      |

### 5.3 `constants`

| Field        | Type   | Required | Notes                                                      |
| ------------ | ------ | -------- | ---------------------------------------------------------- |
| `policyRef`  | string | yes      | Identifier that ties the baked policy to configuration.    |
| `policy`     | object | yes      | Arbitrary policy payload; consumers must treat as opaque.  |

### 5.4 `inputs_schema`

- Type: object.
- Contains either a JSON Schema fragment or structured metadata understood by the runtime.
- Runtimes that cannot validate inputs may pass it through unchanged.

### 5.5 `graph`

| Field   | Type   | Required | Notes                         |
| ------- | ------ | -------- | ----------------------------- |
| `nodes` | array  | yes      | Ordered list of flow steps.   |
| `edges` | array  | yes      | Directed edges between nodes. |

#### 5.5.1 Node Object

| Field         | Type    | Required | Notes                                                                 |
| ------------- | ------- | -------- | --------------------------------------------------------------------- |
| `id`          | string  | yes      | Globally unique within the flow.                                     |
| `type`        | string  | yes      | Step kind (e.g. `http.get`, `mcp.call`).                             |
| `with`        | object  | yes      | Step parameters. Treated as opaque by the compiler; validated by runtime. |
| `timeout_ms`  | integer | yes      | Step-level timeout. `0` implies no explicit timeout (runtime may cap). |
| `retry`       | object  | yes      | Retry policy; see below.                                             |

Retry object fields:

| Field        | Type    | Required | Notes                                                         |
| ------------ | ------- | -------- | ------------------------------------------------------------- |
| `max`        | integer | yes      | Maximum retry attempts (>= 0).                                |
| `backoff_ms` | integer | yes      | Backoff in milliseconds applied between retries (>= 0).       |

Additional fields may be added in `1.y.z` releases; runtimes must ignore unknown properties.

#### 5.5.2 Edge Object

| Field | Type   | Required | Notes                                                          |
| ----- | ------ | -------- | -------------------------------------------------------------- |
| `from` | string | yes     | Source node id.                                                |
| `to`   | string | yes     | Destination node id.                                           |
| `on`   | string | yes     | Transition reason: `success` or `failure`. Future values allowed. |

### 5.6 `metadata`

| Field          | Type   | Required | Notes                                                          |
| -------------- | ------ | -------- | -------------------------------------------------------------- |
| `generated_at` | string | yes      | RFC 3339 timestamp produced by the compiler.                   |
| `source_file`  | string | yes      | Absolute or workspace-relative path of the DSL source file.    |

Additional metadata fields may appear in minor releases.

## 6. Validation Rules

1. All strings must be non-empty.
2. Identifiers (`flow.name`, `node.id`) must match `^[a-zA-Z0-9_.-]+$`.
3. `graph.nodes` must contain at least one element. Node ids must be unique.
4. `graph.edges` may be empty; when present, each `from` and `to` must reference existing node ids.
5. `graph.edges[].on` must be one of the values declared in the schema enumeration. Unknown values are invalid.
6. `timeout_ms` and retry fields must be integers within 0 ≤ value ≤ 2^31-1.
7. `metadata.generated_at` must parse as RFC 3339 UTC timestamp.
8. The document must conform to `docs/ir/v0.1/schema.json`. Validation failures map to CLI exit code `2`.

## 7. Manifest Contract

`out/dsl/manifest.json` is refreshed atomically on each compile. It contains an array of objects shaped as:

```json
{
  "name": "plant.monitor",
  "source_file": "examples/dsl/opcua/flows/plant-monitor.wdl.yaml",
  "policyRef": "maint.default",
  "step_kinds": ["http.get", "mcp.call"],
  "inputs_schema_hash": "sha256:deadbeef...",
  "ir_path": "out/dsl/flows/plant.monitor.ir.json"
}
```

- Only flows emitted in the current compile appear.
- Removed flows are pruned from the manifest.
- `inputs_schema_hash` is calculated using SHA-256 over the canonical JSON representation of `inputs_schema`.
- Projects choose a single runtime implementation at `tm init`. The manifest represents flows compatible with that runtime and its language-bound plugin bundle (e.g. C runtime ↔ C plugins). Multi-runtime manifests are out of scope for v1.0.0.

## 8. Generation Pipeline Responsibilities

1. Normalize source DSL and evaluate policies in Python.
2. Bake policy data into the `constants.policy` object.
3. Emit IR document and validate against the JSON Schema.
4. Write IR to `out/dsl/flows/`.
5. Rebuild `manifest.json` atomically.
6. Optionally update cache structures for incremental builds.

All steps must produce deterministic output for a given source tree, ensuring reproducible builds and stable git diffs.

## 9. Runtime Expectations

Runtimes must:

- Validate the IR version and fail with a `Validation` error if unsupported.
- Enforce flow and step timeouts respecting the values provided, subject to runtime caps.
- Reject unsupported step kinds during capability negotiation (see REP spec).
- Treat `constants.policy` as read-only data.

## 10. Future Evolution

The following extensions are explicitly deferred beyond v1.0.0:

- Richer retry policies (decorrelated jitter, exponential).
- Inline asset blobs and referenced artifacts.
- Embedded observability hooks.

Changes to introduce these features require either a compatible minor release (if additive) or a major version bump.
