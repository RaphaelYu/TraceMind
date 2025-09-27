# Policy Recipes and Runtime Contract

This guide explains how to describe policies using the `recipes-v1` schema, how
those policies connect to the TraceMind tuner, and how to integrate external
MCP (Model Context Protocol) endpoints for closed-loop updates.

## 1. Policy Recipe Format

A policy recipe is a JSON or YAML document with a single `policy` object:

```json
{
  "policy": {
    "id": "checkout-routing",
    "strategy": "epsilon",
    "params": {"epsilon": 0.2},
    "arms": ["flow_a", "flow_b"],
    "endpoint": "mcp:policy"
  }
}
```

Field semantics:

| Field | Type | Description |
| --- | --- | --- |
| `id` | string | Required unique identifier. Present in `tuner.choose/update`. |
| `strategy` | string | Strategy name understood by the tuner. Built-ins: `epsilon`, `ucb`. |
| `params` | object | Optional strategy parameters (`epsilon`, `alpha`, `exploration_bonus`, etc.). |
| `arms` | array of string | Optional hint listing known arms (e.g., candidate flows). |
| `endpoint` | string | Optional MCP endpoint (`mcp:policy` style) for remote updates. |

Recipes can be loaded via `PolicyLoader`:

```python
from tm.ai.policy_registry import PolicyLoader, apply_policy
from tm.ai.tuner import BanditTuner

loader = PolicyLoader()
loader.load("policies/checkout-routing.json")
tuner = BanditTuner(alpha=0.3, exploration_bonus=0.0)
await apply_policy(tuner, "checkout-routing")
```

`apply_policy` wires the loaded `params` into the `BanditTuner` so subsequent
`choose`/`update` calls use the configured strategy.

## 2. Tuner Contract

The runtime interacts with the tuner via two async methods:

```python
arm = await tuner.choose(binding_key, candidates)
await tuner.update(binding_key, arm, reward)
```

* `binding_key` – typically `<model>:<operation>`; use policy `id` for custom
  dispatch.
* `candidates` – list of available arms (`flow` names).
* `reward` – numeric feedback applied after each run.

### 2.1 Observing Bias in an A/B Scenario

1. Load an epsilon policy whose arms are `flow_a` (baseline) and `flow_b` (variant).

   ```python
   loader.load({
       "policy": {
           "id": "demo:read",
           "strategy": "epsilon",
           "params": {"epsilon": 0.2},
           "arms": ["flow_a", "flow_b"]
       }
   })
   await apply_policy(tuner, "demo:read")
   ```

2. Run multiple rounds, granting higher reward to `flow_b`:

   ```python
   counts = {"flow_a": 0, "flow_b": 0}
   for _ in range(200):
       arm = await tuner.choose("demo:read", ["flow_a", "flow_b"])
       counts[arm] += 1
       reward = 1.0 if arm == "flow_b" else 0.0
       await tuner.update("demo:read", arm, reward)
   print(counts)
   ```

   After enough iterations the count for `flow_b` grows larger, indicating the
   epsilon strategy is favouring the higher-reward arm.

## 3. MCP Endpoint Integration

When `policy.endpoint` starts with `mcp:`, the runtime can delegate policy
updates to an MCP server (see `McpPolicyAdapter`). A mock setup for local testing:

```python
from tm.ai.policy_adapter import AsyncMcpClient, BindingPolicy, McpPolicyAdapter
from tm.ai.policy_registry import PolicyLoader
from tm.ai.tuner import BanditTuner

# 1. Load the recipe (endpoint field present)
loader = PolicyLoader()
definition = loader.load("policies/checkout-routing.json")

# 2. Provide a mock MCP transport
async def mock_handler(payload):
    method = payload["method"]
    if method.endswith("get"):
        return {"result": {"version": "remote-1", "params": {"epsilon": 0.1}}}
    if method.endswith("update"):
        return {"result": {"version": "remote-2", "params": {"epsilon": 0.05}}}
    return {"result": {}}

adapter = McpPolicyAdapter(BanditTuner(), AsyncMcpClient(transport=mock_handler))
adapter.register_binding("demo:read", BindingPolicy(endpoint=definition.endpoint, policy_ref=definition.policy_id))
```

The adapter fetches remote parameters during `prepare` and posts rewards during
`post_run`. Real deployments replace `mock_handler` with an HTTP client that
speaks JSON-RPC to the MCP service.

## 4. Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `PolicyError: policy.strategy must be a non-empty string` | Missing or empty `strategy`. | Provide `epsilon`, `ucb`, or custom string with hooks. |
| `PolicyError: policy.arms must be a list of strings` | `arms` contains non-string entries. | Ensure each arm is a string. |
| Tuner keeps exploring both arms equally | Exploration rate too high. | Lower `epsilon` or adjust `confidence` for `ucb`. |
| MCP adapter logs `fallback` | Remote call failed or returned empty response. | Inspect network/logs; ensure remote returns `{"params": {...}}`. |

With these recipes and integration points you can route traffic between flow
variants, observe tuner bias over time, and close the loop with an MCP policy
service.
