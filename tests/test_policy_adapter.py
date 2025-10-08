import pytest
from tm.policy.adapter import PolicyAdapter
from tm.policy.local_store import LocalPolicyStore
from tm.policy.mcp_client import MCPClient
from tm.policy.transports import InProcessTransport


@pytest.mark.asyncio
async def test_fallback_local_only():
    adapter = PolicyAdapter(mcp=None, local=LocalPolicyStore())
    await adapter.update("arm1", {"x": 1})
    assert await adapter.get("arm1") == {"x": 1}
    assert await adapter.list_arms() == ["arm1"]


def _handler_ok(req):
    if req.get("method") == "policy.get":
        return {"jsonrpc": "2.0", "id": req["id"], "result": {"x": 99}}
    if req.get("method") == "policy.update":
        return {"jsonrpc": "2.0", "id": req["id"], "result": req["params"]["params"]}
    if req.get("method") == "policy.list_arms":
        return {"jsonrpc": "2.0", "id": req["id"], "result": ["armA", "armB"]}
    return {"jsonrpc": "2.0", "id": req["id"], "error": {"code": -32601, "message": "Method not found"}}


@pytest.mark.asyncio
async def test_remote_then_local_sync():
    client = MCPClient(InProcessTransport(_handler_ok))
    local = LocalPolicyStore()
    adapter = PolicyAdapter(mcp=client, local=local, timeout_s=2.0, prefer_remote=True)
    assert await adapter.get("armA") == {"x": 99}
    # remote update should also sync local
    newp = await adapter.update("armZ", {"y": 7})
    assert newp == {"y": 7}
    assert await local.get("armZ") == {"y": 7}
    # list from remote
    assert await adapter.list_arms() == ["armA", "armB"]


@pytest.mark.asyncio
async def test_remote_fail_fallback_local():
    # handler that raises to simulate remote outage
    def _handler_raise(req):
        raise RuntimeError("down")

    client = MCPClient(InProcessTransport(_handler_raise))
    local = LocalPolicyStore()
    adapter = PolicyAdapter(mcp=client, local=local, timeout_s=0.01, prefer_remote=True)
    # local path should still work
    await adapter.update("armL", {"k": 5})
    assert await adapter.get("armL") == {"k": 5}
    assert await adapter.list_arms() == ["armL"]
