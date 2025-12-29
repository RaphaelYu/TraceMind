# Derive Agent Bundle v0

TraceMind codex agents consume an `intent` candidate and emit the artifacts required to run the derived workflow. Your response must include four complete artifact documents (envelope + body) serialized in YAML, one each for:

1. A `capabilities` candidate that captures how the intent translates into capabilities (inputs, outputs, constraints, execution_binding).
2. An `agent_bundle` candidate that wires one or more runtime agents (e.g., noop, http-mock, shell) together to satisfy the intent goal, including IO contract metadata (`preconditions`, `policy.allow`, `plan` steps, and agent specs).
3. A `gap_map` candidate that describes any missing pieces discovered during derivation (empty gaps are acceptable if derivation succeeded).
4. A `backlog` candidate that records follow-up work items or reinforces the derivation outcome.

Each artifact must follow the TraceMind envelope schema: `artifact_id`, `status`, `artifact_type`, `version`, `created_by`, `created_at`, `body_hash`, `envelope_hash`, and `meta` (e.g., `phase`, `derived_from`). Bodies must respect their respective schema (see `tm.artifacts.models`).  

For example:

```yaml
envelope:
  artifact_id: tm-agent-bundle-demo
  status: candidate
  artifact_type: agent_bundle
  version: v0
  created_by: codex-deriver
  created_at: "2024-01-01T10:00:00Z"
  body_hash: ""
  envelope_hash: ""
  meta:
    phase: derived
body:
  bundle_id: tm-bundle/derived-notify
  ...
```

Ensure the agent bundle plan steps align with the IO contract defined in `TM-SPEC-IO-CONTRACT-V0`, include idempotency keys, and declare policy allowlists for resource effects. If verification would fail, highlight the errors in the `gap_map` and `backlog` artifact bodies so humans can take action.
