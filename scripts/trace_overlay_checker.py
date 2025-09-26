#!/usr/bin/env python3
"""Overlay FlowTrace events onto exported FlowSpec artifacts."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict, deque
from pathlib import Path
from typing import Dict, List

from tm.storage.binlog import BinaryLogReader


def load_artifacts(artifact_dir: Path) -> Dict[str, Dict[str, set[str]]]:
    mapping: Dict[str, Dict[str, set[str]]] = {}
    for flow_dir in artifact_dir.iterdir():
        if not flow_dir.is_dir():
            continue
        rev_map: Dict[str, set[str]] = {}
        for file in flow_dir.glob("flow-*.json"):
            data = json.loads(file.read_text("utf-8"))
            rev = data.get("flow_rev")
            steps = {step["name"] for step in data.get("steps", [])}
            if rev:
                rev_map[rev] = steps
        if not rev_map:
            latest_file = flow_dir / "flow.json"
            if latest_file.exists():
                data = json.loads(latest_file.read_text("utf-8"))
                rev = data.get("flow_rev", "rev-1")
                rev_map[rev] = {step["name"] for step in data.get("steps", [])}
        if rev_map:
            mapping[flow_dir.name] = rev_map
    return mapping


def collect_runs(reader: BinaryLogReader, limit: int) -> Dict[str, List[dict]]:
    runs: Dict[str, deque] = {}
    order: deque = deque()
    for etype, payload in reader.scan():
        if etype != "FlowTrace":
            continue
        event = json.loads(payload.decode("utf-8"))
        run_id = event.get("run_id")
        if not run_id:
            continue
        if run_id not in runs:
            runs[run_id] = deque()
            order.append(run_id)
            if len(order) > limit:
                old = order.popleft()
                runs.pop(old, None)
        runs[run_id].append(event)
    return {rid: list(events) for rid, events in runs.items()}


def analyze(runs: Dict[str, List[dict]], artifacts: Dict[str, Dict[str, set[str]]]) -> Dict[str, object]:
    anomalies = []
    total_events = 0

    for run_id, events in runs.items():
        events.sort(key=lambda e: e.get("seq", 0))
        for event in events:
            total_events += 1
            flow = event.get("flow")
            flow_rev = event.get("flow_rev")
            step = event.get("step")
            flow_map = artifacts.get(flow)
            if not flow_map:
                anomalies.append({
                    "run_id": run_id,
                    "reason": "FLOW_NOT_FOUND",
                    "flow": flow,
                    "flow_rev": flow_rev,
                    "step": step,
                })
                continue
            step_set = flow_map.get(flow_rev)
            if step_set is None:
                anomalies.append({
                    "run_id": run_id,
                    "reason": "REV_NOT_FOUND",
                    "flow": flow,
                    "flow_rev": flow_rev,
                    "step": step,
                })
                continue
            if step not in step_set:
                anomalies.append({
                    "run_id": run_id,
                    "reason": "STEP_NOT_FOUND",
                    "flow": flow,
                    "flow_rev": flow_rev,
                    "step": step,
                })
    return {
        "runs_analyzed": len(runs),
        "events": total_events,
        "anomalies": anomalies,
        "anomaly_rate": len(anomalies) / total_events if total_events else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="FlowTrace overlay checker")
    parser.add_argument("--trace-dir", required=True, help="directory containing FlowTrace binlogs")
    parser.add_argument("--artifacts-dir", required=True, help="directory with exported flow artifacts")
    parser.add_argument("--runs", type=int, default=10, help="number of recent runs to analyze")
    args = parser.parse_args()

    artifacts = load_artifacts(Path(args.artifacts_dir))
    reader = BinaryLogReader(args.trace_dir)
    runs = collect_runs(reader, args.runs)
    report = analyze(runs, artifacts)

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
