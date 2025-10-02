# MCP Policy Adapter (T-POLICY-02)

This adapter fetches/updates policy parameters via MCP (JSON-RPC 2.0) with non-blocking IO and graceful fallback to a local store.

## Quick start (local-only fallback)
```python
import asyncio
from tm.policy.adapter import PolicyAdapter
from tm.policy.local_store import LocalPolicyStore

async def main():
    adapter = PolicyAdapter(mcp=None, local=LocalPolicyStore())
    await adapter.update("arm_A", {"alpha": 0.1})
    print(await adapter.get("arm_A"))
    print(await adapter.list_arms())

asyncio.run(main())
```

## With a dummy in-process MCP transport
```python
import asyncio
from tm.policy.adapter import PolicyAdapter
from tm.policy.local_store import LocalPolicyStore
from tm.policy.mcp_client import MCPClient
from tm.policy.transports import InProcessTransport

# Fake MCP server
def handler(req):
    if req.get("method") == "policy.get":
        return {"jsonrpc": "2.0", "id": req["id"], "result": {"alpha": 0.3}}
    if req.get("method") == "policy.update":
        return {"jsonrpc": "2.0", "id": req["id"], "result": req["params"]["params"]}
    if req.get("method") == "policy.list_arms":
        return {"jsonrpc": "2.0", "id": req["id"], "result": ["arm_A", "arm_B"]}
    return {"jsonrpc": "2.0", "id": req["id"], "error": {"code": -32601, "message": "Method not found"}}

async def main():
    client = MCPClient(InProcessTransport(handler))
    adapter = PolicyAdapter(mcp=client, local=LocalPolicyStore(), timeout_s=2.0, prefer_remote=True)
    print(await adapter.get("arm_A"))      # -> from MCP
    print(await adapter.update("arm_X", {"beta": 42}))  # -> MCP update
    print(await adapter.list_arms())       # -> MCP list

asyncio.run(main())
```

## Offline evaluation workflow

After a tuning session you can replay historical run records to compare arms without
touching the live control loop. The helper script `scripts/offline_eval.py` accepts
the JSONL trace emitted by `trace-mind` (or any equivalent export) and produces both
a console table and a structured report under `reports/offline_eval.json`.

```bash
PYTHONPATH=. python scripts/offline_eval.py \
    --from-jsonl tests/data/sample_runs.jsonl \
    --baseline-sec 3600 \
    --recent-sec 600 \
    --binding demo:read
```

Key columns:

- `n`: number of runs inside the window (`--recent-sec` by default).
- `ok_rate`: share of successful runs.
- `latency_ms` / `cost_usd`: arithmetic averages in the window.
- `reward`: averaged reward using the configured weights (defaults from `trace-mind.toml`).
- `Δreward`: difference between the recent window and the baseline window (`--baseline-sec`).

The JSON artefact mirrors the same metrics so CI/CD jobs can diff or visualise them:

```json
{
  "params": {"baseline_sec": 3600.0, "recent_sec": 600.0, "binding_filter": "demo:read"},
  "bindings": {
    "demo:read": {
      "flow_fast": {"recent": {...}, "baseline": {...}, "delta": {...}},
      "flow_slow": {"recent": {...}, "baseline": {...}, "delta": {...}}
    }
  }
}
```

Use the reward deltas to spot which arms improved (positive) or regressed (negative).
