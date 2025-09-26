from tm.flow.operations import Operation
from tm.flow.spec import FlowSpec, StepDef


def test_flow_spec_revision_changes_on_add():
    spec = FlowSpec(name="demo")
    rev1 = spec.flow_revision()
    spec.add_step(StepDef("start", Operation.TASK))
    rev2 = spec.flow_revision()
    assert rev1.startswith("rev-")
    assert rev2.startswith("rev-")
    assert rev1 != rev2
    assert spec.flow_id == "demo"


def test_flow_spec_custom_id():
    spec = FlowSpec(name="demo", flow_id="flow-123")
    assert spec.flow_id == "flow-123"


def test_flow_spec_step_id_stable_for_same_flow():
    spec1 = FlowSpec(name="demo")
    spec1.add_step(StepDef("start", Operation.TASK))
    sid1 = spec1.step_id("start")

    spec2 = FlowSpec(name="demo")
    spec2.add_step(StepDef("start", Operation.TASK))
    sid2 = spec2.step_id("start")

    assert sid1 == sid2
    assert sid1.startswith("step-")


def test_flow_spec_revision_reflects_config_change():
    base = FlowSpec(name="demo")
    base.add_step(StepDef("start", Operation.TASK, config={"route": "left"}))
    rev1 = base.flow_revision()

    modified = FlowSpec(name="demo")
    modified.add_step(StepDef("start", Operation.TASK, config={"route": "right"}))

    assert modified.flow_revision() != rev1
