from tm.flow.operations import Operation
from tm.flow.spec import FlowSpec, StepDef


def test_flow_spec_revision_changes_on_add():
    spec = FlowSpec(name="demo")
    rev1 = spec.flow_revision()
    spec.add_step(StepDef("start", Operation.TASK))
    rev2 = spec.flow_revision()
    assert rev1 != rev2
    assert spec.flow_id == "demo"


def test_flow_spec_custom_id():
    spec = FlowSpec(name="demo", flow_id="flow-123")
    assert spec.flow_id == "flow-123"
