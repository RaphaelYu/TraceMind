# Validation & Simulation Guide

TraceMind ships a family of CLI commands that help you spot configuration mistakes before running an agent.  This guide walks through the four primary tools—`flow lint`, `flow plan`, `validate`, and `simulate`—and provides copy/paste examples that you can run as-is.

All commands assume you are at the repository root (the same directory that contains this guide).

## Quick reference

| Command | Purpose | Exit code |
|---------|---------|-----------|
| `tm flow lint …` | Structural checks (cycles, unreachable steps, bad locks) | `0` success, `1` defects |
| `tm flow plan …` | Produce layered DAG and stats (depth, width, branch factor) | `0` success, `1` if the planner fails |
| `tm validate …` | Cross-flow/policy analysis (locks, cron overlaps, policy arm collisions) | `0` success, `1` conflicts |
| `tm simulate run …` | Deterministic, time-stepped execution with lock scheduling | `0` success, `1` deadlocks/starvation detected |

## `tm flow lint`

Run the linter against one or more flow YAML files.  The examples below use the fixtures that ship with the repository.

```bash
# Passes: no structural issues
tm flow lint fixtures/flows/tiny_ok.yml

# Fails: cycle between steps a -> b -> a
tm flow lint fixtures/flows/has_cycle.yml
```

## `tm flow plan`

The planner creates a layered DAG and reports metrics about the topology.  Use `--json` to integrate the output with automation or snapshot tests.

```bash
tm flow plan fixtures/flows/wide_deep.yml --json
```

The JSON response contains the ordered layers, node count, depth, maximum width, and the maximum out-degree.  When the planner cannot build a DAG (for example, because of a cycle) it returns a non-zero exit code.

## `tm validate`

`tm validate` inspects flows and policies together, looking for lock conflicts, cron schedule overlaps, and policy arm collisions.  The command accepts glob patterns or explicit filenames.

```bash
# Report policy arm overlap (non-zero exit)
tm validate --flows fixtures/flows/tiny_ok.yml \
            --policies fixtures/policies/arms_overlap.yml \
            --json

# Exit 0 when no conflicts are present
tm validate --flows fixtures/flows/tiny_ok.yml \
            --policies fixtures/policies/arms_overlap.yml \
            --json \
            --env TM_FLOW_WARN_MAX_DEPTH=10
```

Tip: set `TM_FLOW_WARN_MAX_DEPTH`, `TM_FLOW_ERROR_MAX_DEPTH`, `TM_FLOW_WARN_MAX_NODES`, or `TM_FLOW_WARN_MAX_OUT_DEGREE` to configure advisory thresholds without editing files.

## `tm simulate run`

The simulator executes flows in a deterministic, lock-aware scheduler.  It is particularly handy for verifying deadlock scenarios.

```bash
# Shared locks – finishes without deadlocks
tm simulate run --flow fixtures/flows/shared_readers.yml --json

# Exclusive lock deadlock example (returns exit code 1)
tm simulate run --flow fixtures/flows/exclusive_db.yml --json
echo $?  # prints 1
```

The JSON payload includes `finished`, `deadlocks`, and the event trace.  Use `--seed` to vary the scheduling order while keeping runs reproducible.

## Integrating with CI

- The repository’s CI matrix runs `tm flow lint`, `tm flow plan`, `tm validate`, and `tm simulate run` against fixtures so regressions are caught automatically.
- Add additional checks by invoking the same commands in your project pipeline.  Each command is idempotent and safe to run in read-only environments.

Need more detail?  Explore the implementations in `tm/validate/static.py` and `tm/validate/simulator.py`, or open a discussion in the issue tracker for suggestions and enhancements.
