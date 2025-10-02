# Safety Governance

TraceMind v0.6 adds budgets, rate limits, and circuit breakers that can be enabled from `trace-mind.toml`.

## Budgets & Rate Limits

Budgets track rolling token and USD usage. Rate limits control QPS and in-flight concurrency. Config hierarchy: global → flow → policy arm.

```toml
[governance]
enabled = true

[governance.limits]
enabled = true

[governance.limits.global]
qps = 2000
concurrency = 500
tokens_per_min = 200000
cost_per_hour = 5.0

[governance.limits.flow.intelligent_loop]
qps = 300
cost_per_hour = 0.8

[governance.limits.policy."demo:read".arm.fast]
tokens_per_min = 50000
```

Metrics are exposed through `tm_govern_qps_limited_total`, `tm_govern_budget_exceeded_total`, and `tm_govern_budget_usage{kind}`. Use `_recorder.get_stats()` to inspect rejection counts.

## Circuit Breakers

Circuit breakers prevent repeated failures and timeouts.

```toml
[governance.breaker]
enabled = true

[governance.breaker.global]
window_sec = 30
failure_threshold = 5
timeout_threshold = 3
cooldown_sec = 15
half_open_max_calls = 2
```

Metrics include `tm_breaker_state{target}` (0 closed, 0.5 half-open, 1 open) and `tm_breaker_trips_total`.

## Runtime Integration

`FlowRuntime` enforces guard rails before requests enter the queue. Rejections return envelopes such as:

```json
{
  "status": "rejected",
  "error_code": "RATE_LIMITED",
  "flow": "demo"
}
```

`GovernanceManager` can also be constructed manually:

```python
from tm.governance.manager import GovernanceManager
from tm.governance.config import load_governance_config

go = GovernanceManager(load_governance_config("trace-mind.toml"))
runtime = FlowRuntime(flows, governance=go)
```

See `docs/guard.md` and `docs/hitl.md` for guardrails and human approvals.
