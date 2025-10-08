import pytest

from tm.flow.correlate import CorrelationHub
from tm.flow.operations import Operation, ResponseMode
from tm.flow.policies import FlowPolicies
from tm.flow.runtime import FlowRuntime
from tm.flow.spec import FlowSpec, StepDef


class DummyFlow:
    def __init__(self, spec: FlowSpec):
        self._spec = spec

    @property
    def name(self) -> str:
        return self._spec.name

    def spec(self) -> FlowSpec:
        return self._spec


class RecordingHub(CorrelationHub):
    def __init__(self):
        super().__init__()
        self.signals: dict[str, dict] = {}

    def signal(self, req_id: str, payload: dict) -> None:
        self.signals[req_id] = dict(payload)
        super().signal(req_id, payload)


def _deferred_spec(name: str, hub: RecordingHub) -> FlowSpec:
    spec = FlowSpec(name=name)
    spec.add_step(StepDef("build", Operation.TASK, next_steps=("notify",)))

    def _notify(ctx):
        hub.signal(ctx["req_id"], {"status": "ready", "ok": True})

    spec.add_step(
        StepDef(
            "notify",
            Operation.TASK,
            next_steps=(),
            config={"callable": _notify},
        )
    )
    return spec


def test_flow_runtime_lookup_and_registration():
    spec = FlowSpec(name="lookup")
    flow = DummyFlow(spec)
    runtime = FlowRuntime()

    runtime.register(flow)

    chosen = runtime.choose_flow("lookup")
    assert chosen is flow
    assert runtime.build_dag(chosen) is spec

    with pytest.raises(KeyError):
        runtime.choose_flow("missing")


@pytest.mark.asyncio
async def test_deferred_flow_records_signal_payload():
    hub = RecordingHub()
    spec = _deferred_spec("async", hub)
    flow = DummyFlow(spec)
    runtime = FlowRuntime(
        {spec.name: flow},
        policies=FlowPolicies(response_mode=ResponseMode.DEFERRED, allow_deferred=True, short_wait_s=0.01),
        correlator=hub,
    )

    request = {"req_id": "REQ-1"}
    response = await runtime.run("async", inputs=request)

    assert response["status"] == "ok"
    token = response["output"]["token"]

    signal_fn = spec.step("notify").config["callable"]
    signal_fn({"req_id": request["req_id"]})

    assert hub.signals["REQ-1"] == {"status": "ready", "ok": True}
    stored = hub.resolve(token)
    assert stored is not None and stored[1]["req_id"] == "REQ-1"

    await runtime.aclose()


@pytest.mark.asyncio
async def test_deferred_flow_ready_when_signal_precedes_run():
    hub = RecordingHub()
    spec = _deferred_spec("async", hub)
    flow = DummyFlow(spec)
    runtime = FlowRuntime(
        {spec.name: flow},
        policies=FlowPolicies(response_mode=ResponseMode.DEFERRED, allow_deferred=True, short_wait_s=0.01),
        correlator=hub,
    )

    request = {"req_id": "REQ-2"}
    spec.step("notify").config["callable"]({"req_id": request["req_id"]})

    response = await runtime.run("async", inputs=request)

    assert response["status"] == "ok"
    assert response["output"]["status"] == "ready"
    assert response["output"]["result"] == {"status": "ready", "ok": True}

    await runtime.aclose()
