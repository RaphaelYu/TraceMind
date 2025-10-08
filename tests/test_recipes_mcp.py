from tm.flow.correlate import CorrelationHub
from tm.recipes.mcp_flows import mcp_tool_call


class DummyMcpClient:
    def __init__(self):
        self.calls = []

    def call(self, tool, method, params):
        self.calls.append((tool, method, params))
        return {"ok": True, "params": params}


def test_mcp_recipe_call_and_signal():
    spec = mcp_tool_call("files", "list", ["path"])
    hub = CorrelationHub()
    ctx = {
        "inputs": {"path": "/tmp"},
        "clients": {"mcp": DummyMcpClient()},
        "correlator": hub,
        "req_id": "REQ-2",
    }

    build_fn = spec.step("build").config["callable"]
    call_fn = spec.step("call").config["callable"]
    signal_fn = spec.step("signal").config["callable"]

    build_fn(ctx)
    call_fn(ctx)

    assert ctx["clients"]["mcp"].calls == [("files", "list", {"path": "/tmp"})]
    assert ctx["result"] == {"ok": True, "params": {"path": "/tmp"}}

    signal_fn(ctx)

    assert hub.poll("REQ-2") == {"status": "ready", "data": {"ok": True, "params": {"path": "/tmp"}}}
    assert ctx["response"] == {"status": "ready", "data": {"ok": True, "params": {"path": "/tmp"}}}
