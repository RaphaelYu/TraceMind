import json

from tm.flow.artifacts import export_flow_artifact
from tm.flow.operations import Operation
from tm.flow.spec import FlowSpec, StepDef


def test_export_flow_artifact_creates_json_and_dot(tmp_path):
    spec = FlowSpec(name="demo")
    spec.add_step(StepDef("start", Operation.TASK, next_steps=("finish",)))
    spec.add_step(StepDef("finish", Operation.FINISH))

    artifact = export_flow_artifact(spec, tmp_path)

    assert artifact.json_path.exists()
    assert artifact.dot_path.exists()

    data = json.loads(artifact.json_path.read_text("utf-8"))
    assert data["flow_id"] == "demo"
    assert data["flow_rev"] == spec.flow_revision()
    node_names = {node["name"] for node in data["nodes"]}
    assert node_names == {"start", "finish"}
    edges = {(edge["from"], edge["to"]) for edge in data["edges"]}
    assert edges == {("start", "finish")}

    dot = artifact.dot_path.read_text("utf-8")
    assert "digraph \"demo@" in dot
    assert "start" in dot and spec.step_id("start") in dot
