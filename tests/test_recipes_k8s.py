import pytest

from tm.flow.correlate import CorrelationHub
from tm.flow.operations import ResponseMode
from tm.flow.policies import FlowPolicies
from tm.flow.runtime import FlowRuntime
from tm.recipes.k8s_flows import pod_health_check


class _FlowWrapper:
    def __init__(self, spec):
        self._spec = spec

    @property
    def name(self):
        return self._spec.name

    def spec(self):
        return self._spec


@pytest.mark.asyncio
async def test_pod_health_flow_pending_then_ready():
    spec = pod_health_check(namespace="default", label_selector="app=demo")
    hub = CorrelationHub()
    runtime = FlowRuntime(
        {spec.name: _FlowWrapper(spec)},
        policies=FlowPolicies(response_mode=ResponseMode.DEFERRED),
        correlator=hub,
    )

    body = {"req_id": "REQ-1", "flow": spec.name}
    pending = await runtime.run(spec.name, inputs=body, response_mode=ResponseMode.DEFERRED)

    assert pending["status"] == "ok"
    assert pending["output"]["status"] == "pending"
    assert pending["output"]["token"]

    hub.signal("REQ-1", {"status": "ready", "data": {"pods": []}})

    ready = await runtime.run(spec.name, inputs=body, response_mode=ResponseMode.DEFERRED)

    assert ready["status"] == "ok"
    assert ready["output"]["status"] == "ready"
    assert ready["output"]["result"] == {"status": "ready", "data": {"pods": []}}
