# Controller Cycle CLI

`tm controller cycle` wraps a full Observe → Decide → Act loop so you can verify controller artifacts and get deterministic evidence in a single command.

## Usage

```
tm controller cycle --bundle <agent-bundle.yaml> --mode live|replay --report <path> [--dry-run] [--record-path <file>]
```

### Required arguments

- `--bundle`: path to an accepted `agent_bundle` artifact that wires the Observe/Decide/Act agents.
- `--report`: file where the controller run report will be written (YAML when PyYAML is available; falls back to JSON).

### Optional arguments

- `--mode`: `live` (default) uses the DecideAgent’s live LLM call path; `replay` reuses the stored plan without invoking the model.
- `--dry-run`: skip registry updates after the run, useful for local experimentation.
- `--record-path`: destination for DecideAgent’s replay store (default `.tracemind/controller_decide_records.json`).

## Behavior

1. Load the provided bundle and execute its plan step-by-step (observe → decide → act).
2. Verify each controller artifact (`EnvSnapshot`, `ProposedChangePlan`, `ExecutionReport`) through the artifact verifier so their body hashes become stable.
3. Evaluate the plan’s policy requirements before the Act step runs; the cycle halts if guards deny a target.
4. Persist the accepted controller artifacts to `controller_artifacts/` beside the report and register them unless `--dry-run` is set.
5. Emit `gap_map.yaml` and `backlog.yaml` beside the report when the cycle fails, so reviewers can act on the recorded issues.

Use `--mode replay` with a recorded plan to reproduce decisions without calling an LLM; the runner still verifies the replayed plan and enforces policy before acting.
