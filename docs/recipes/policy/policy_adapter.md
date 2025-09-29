# Recipe: Policy Adapter (MCP with fallback)

Local-only (fallback) quick start:

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

Fake MCP transport:

```python
from tm.policy.mcp_client import MCPClient
from tm.policy.transports import InProcessTransport

def handler(req):
    if req.get("method") == "policy.get":
        return {"jsonrpc": "2.0", "id": req["id"], "result": {"alpha": 0.3}}
    if req.get("method") == "policy.update":
        return {"jsonrpc": "2.0", "id": req["id"], "result": req["params"]["params"]}
    if req.get("method") == "policy.list_arms":
        return {"jsonrpc": "2.0", "id": req["id"], "result": ["arm_A", "arm_B"]}
    return {"jsonrpc": "2.0", "id": req["id"], "error": {"code": -32601, "message": "Method not found"}}
```
