import pytest

from tm.flow.runtime import FlowRuntime
from tm.flow.spec import FlowSpec


class DummyFlow:
    def __init__(self, spec: FlowSpec):
        self._spec = spec

    @property
    def name(self) -> str:
        return self._spec.name

    def spec(self) -> FlowSpec:
        return self._spec


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

