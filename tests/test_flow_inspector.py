from tm.flow.operations import Operation
from tm.flow.spec import FlowSpec, StepDef
from tm.flow.inspector import FlowInspector


def test_inspector_detects_cycle_and_dangling():
    spec = FlowSpec(name="bad")
    spec.add_step(StepDef("a", Operation.TASK, next_steps=("b",)))
    spec.add_step(StepDef("b", Operation.TASK, next_steps=("a", "ghost")))
    inspector = FlowInspector(spec)
    issues = inspector.validate()
    kinds = {issue.kind for issue in issues}
    assert "cycle" in kinds
    assert "dangling" in kinds


def test_inspector_exports_mermaid_and_json(tmp_path):
    spec = FlowSpec(name="doc")
    spec.add_step(StepDef("start", Operation.TASK, next_steps=()))
    inspector = FlowInspector(spec)
    data = inspector.export_json()
    assert data["flow"] == "doc"
    mermaid = inspector.export_mermaid()
    assert "flowchart TD" in mermaid
