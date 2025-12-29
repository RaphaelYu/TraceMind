# Runtime Agent CLI

The `tm run bundle` command executes an accepted `agent_bundle` artifact via the runtime executor and emits a structured run report describing start/end timestamps, per-step outputs, policy decisions, and evidence summaries.

## Command

```tm run bundle <bundle_path> --inputs <ref>=<value>... --report <path> [--json]
```

* `<bundle_path>` points to an accepted `agent_bundle` YAML/JSON artifact.
* `--inputs` may be repeated; values are JSON decoded when possible (files may be referenced via `@path`).
* `--report` designates the path to write the run report.
* `--json` writes the report as JSON; otherwise the report is emitted in YAML (PyYAML is required).

### Example

```tm run bundle bundles/agent-bundle.yaml --inputs artifact:config='{"payload":"value"}' --report run-report.yaml
```

The command prints a brief summary and writes the report; the exit code is `0` if the bundle succeeded and `1` otherwise.

## Run report schema

The report is a mapping with at least the following keys:

- `bundle_id`, `artifact_id`, `body_hash`: artifact identifiers and hash.
- `start_time`, `end_time`, `duration_seconds`: timestamps in ISO8601 UTC.
- `success`, `error`: overall status plus optional error message when execution failed.
- `steps`: list of plan steps describing agents, phases, declared inputs/outputs, and status (`completed`, `pending`, or `failed`).
- `outputs`: the final values stored for each declared output ref.
- `evidence_summary`: total evidence records produced plus counts grouped by kind (events, metrics, idempotency, policy decisions, etc.).
- `policy_decisions`: ordered list of guard evaluations showing which targets were allowed or denied and why.

The report can be used by diagnostics, automation, or governance tooling to correlate execution artifacts with runtime behavior.
