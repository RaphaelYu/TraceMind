# How to Write an Intent Artifact (v0)

Use the `specs/specs/TM-SPEC-ARTIFACTS-V0.md` form to provide the minimal fields TraceMind needs for downstream verification and decomposition.

## Envelope requirements
- `artifact_id`, `version`, `status`: Candidate artefacts are `status: candidate` and later promoted to `accepted` by the verifier.
- `created_by`, `created_at`: Use UTC ISO 8601.
- `body_hash`, `envelope_hash`: Leave empty for drafts; the verifier fills them on acceptance.
- `meta`: Add rollout flags (`{phase: "example"}`), hashes, and any `derived_from` or `invariant_status` info required by consistency checks.

## Body essentials (Intent body)
```yaml
intent_id: TM-INT-0001
title: "Short summary"
context: "Why this matters now"
goal: "Measurable outcome (e.g., improve notification latency by 30%)"
non_goals: ["What we deliberately skip"]
actors: ["user", "system"]
inputs: ["incident.created"]
outputs: ["incident.notification"]
constraints: ["always include severity tags"]
success_metrics: ["95% of notifications in 30s"]
risks: ["alert storms from retries"]
assumptions: ["incident payload includes severity"]
trace_links:
  related_intents: ["TM-INT-0002"]
```

### Traceability notes
- Keep `goal` measurable so the verifier + golden tests can assert `body_hash` stability.
- Use `trace_links` to point to parent or sibling intents so auditors can follow decomposition.

## Working flow
1. Save your intent YAML under `specs/examples/` or a new location and run `tm artifacts verify <path>` to see if the verifier accepts it.
2. If verification succeeds, `tm artifacts accept <path> --out <dir>` writes the accepted artifact (with hashes populated) and registers it. Inspect `.tracemind/registry.jsonl` for new entries.
3. Run `tm artifacts diff current previous` to compare canonical bodies when you tweak the intent.
4. CI runs `tm plan lint` and `tm artifacts verify` on the example artifacts; mimicking that locally helps catch `STEP_IO` or hash regressions early.
