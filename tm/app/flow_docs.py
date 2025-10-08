from __future__ import annotations

import json
from pathlib import Path
from tm.flow.runtime import FlowRuntime
from tm.flow.inspector import FlowInspector


def export_flows(runtime: FlowRuntime, out_dir: str) -> None:
    path = Path(out_dir)
    path.mkdir(parents=True, exist_ok=True)
    for name, flow in runtime._flows.items():  # pragma: no cover - trusted usage
        spec = runtime.build_dag(flow)
        inspector = FlowInspector(spec)
        issues = inspector.validate()
        spec_dir = path / name
        spec_dir.mkdir(exist_ok=True)
        json_payload = inspector.export_json()
        flow_rev = json_payload.get("flow_rev", "rev-1")
        with (spec_dir / "flow.json").open("w", encoding="utf-8") as fh:
            json.dump(json_payload, fh, indent=2)
        with (spec_dir / f"flow-{flow_rev}.json").open("w", encoding="utf-8") as fh:
            json.dump(json_payload, fh, indent=2)
        with (spec_dir / "flow.mmd").open("w", encoding="utf-8") as fh:
            fh.write(inspector.export_mermaid())
        if issues:
            with (spec_dir / "issues.json").open("w", encoding="utf-8") as fh:
                json.dump([i.__dict__ for i in issues], fh, indent=2)
