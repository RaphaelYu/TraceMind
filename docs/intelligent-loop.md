# Intelligent Loop (Plan → Execute → Reflect)

This document explains how to run an autonomous loop with the new
`ai.plan`, `ai.execute_plan`, and `ai.reflect` steps introduced in v0.5.

## Safety Principles

* **JSON-only**: Planner and Reflector must produce valid JSON. The
  steps reject any free-form text or schema violations.
* **Allow-list enforcement**: `ai.plan` only references tools/flows
  included in its `allow` section; `ai.execute_plan` enforces the same
  allow list at runtime and audits violations (`POLICY_FORBIDDEN`).
* **No chain-of-thought**: Neither the planner nor reflector logs or
  returns raw reasoning, only structured outputs.

## Quick Start

1. Configure reward weights and tuner strategy in `trace-mind.toml`.
2. Install optional extras if you need metrics: `pip install -e .[prom]`.
3. Ensure tools/flows referenced by the plan are registered and allow-listed.

## Running the Sample Recipe

We provide a recipe at `examples/intelligent_loop.yaml` that sorts and
summarizes an array. It exercises the entire loop:

```yaml
id: intelligent_loop
steps:
  - id: plan
    type: ai.plan
    provider: fake
    model: planner
    goal: "Sort and deduplicate an array and write a short summary"
    allow:
      tools: ["tool.sort", "tool.unique", "tool.summarize"]
      flows: []
    constraints:
      max_steps: 5
      budget_usd: 0.02
    retries: 1

  - id: run
    type: ai.execute_plan
    plan: "${ctx.plan.plan}"
    runtime: "${helpers.runtime}"
    max_steps: 5

  - id: reflect
    type: ai.reflect
    provider: fake
    model: reflector
    recent_outcomes: "${ctx.run.steps}"
    last_error: "${ctx.run.error}"
    retrospect_stats: "${ctx.meta.retrospect}"
    retries: 1

  - id: maybe_patch
    type: helpers.when
    predicate: "trace_mind.helpers:plan_has_patch"
    then: rerun
    otherwise: done

  - id: rerun
    type: ai.execute_plan
    plan: "${helpers.apply_patch(ctx.run.plan, ctx.reflect.reflection.plan_patch)}"
    runtime: "${helpers.runtime}"

  - id: done
    type: helpers.patch
    mode: merge
    with: { result: "${ctx.run.steps}" }
```

### Helper Steps Referenced

* `helpers.runtime` – resolves to the FlowRuntime instance.
* `helpers.when` – conditional branching.
* `helpers.apply_patch` – applies RFC6902 patch to the original plan.
* `helpers.patch` – merge final outputs into the flow context.

## Metrics

The following metrics are emitted when Prometheus is enabled:

* Counters: `tm_plan_requests_total`, `tm_plan_failures_total`,
  `tm_plan_steps_executed_total`, `tm_plan_retries_total`,
  `tm_reflect_requests_total`, `tm_reflect_failures_total`.
* Gauges: `tm_plan_last_duration_ms`, `tm_reflect_last_duration_ms`.

## Recorder Fields

Each planner invocation records `planning_ms`, `plan_steps`,
`plan_retries`, token usage, and cost. Reflections log duration and
status via `on_reflect_result`.

## Acceptance Checklist

* Goal input triggers `ai.plan` → `ai.execute_plan` → `ai.reflect`.
* Allow-list enforcement blocks disallowed tools/flows.
* Reflection suggests patches when a step fails; patched plan succeeds
  on rerun.
* No raw chain-of-thought appears in logs or responses.
