#!/usr/bin/env python3
"""Overlay FlowTrace events onto exported FlowSpec artifacts."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict, deque
from pathlib import Path
from typing import Dict, List, Set

from tm.storage.binlog import BinaryLogReader


def load_artifacts(artifact_dir: Path) -> Dict[str, Dict[str, Dict[str, Set[str]]]]:
    mapping: Dict[str, Dict[str, Dict[str, Set[str]]]] = defaultdict(dict)

    if not artifact_dir.exists():
        return {}

    for file in artifact_dir.glob("*.json"):
        if not file.is_file():
            continue
        try:
            data = json.loads(file.read_text("utf-8"))
        except json.JSONDecodeError:
            continue
        flow_id = data.get("flow_id") or data.get("flow")
        flow_rev = data.get("flow_rev")
        if not flow_id or not flow_rev:
            continue
        nodes = data.get("nodes")
        step_ids: Set[str] = set()
        step_names: Set[str] = set()
        if isinstance(nodes, list):
            for node in nodes:
                if isinstance(node, dict):
                    sid = node.get("step_id")
                    name = node.get("name")
                    if isinstance(sid, str):
                        step_ids.add(sid)
                    if isinstance(name, str):
                        step_names.add(name)
        # Back-compat for older inspector JSON payloads
        if not nodes and isinstance(data.get("steps"), list):
            for node in data["steps"]:
                if isinstance(node, dict):
                    sid = node.get("step_id")
                    name = node.get("name")
                    if isinstance(sid, str):
                        step_ids.add(sid)
                    if isinstance(name, str):
                        step_names.add(name)

        mapping[flow_id][flow_rev] = {
            "step_ids": step_ids,
            "names": step_names,
        }

    # Legacy directory layout support
    for flow_dir in artifact_dir.iterdir():
        if not flow_dir.is_dir():
            continue
        flow_id = flow_dir.name
        for file in flow_dir.glob("flow-*.json"):
            try:
                data = json.loads(file.read_text("utf-8"))
            except json.JSONDecodeError:
                continue
            rev = data.get("flow_rev")
            if not rev:
                continue
            step_names = {step.get("name") for step in data.get("steps", []) if isinstance(step, dict)}
            mapping[flow_id].setdefault(rev, {"step_ids": set(), "names": set()})
            mapping[flow_id][rev]["names"].update({name for name in step_names if isinstance(name, str)})

    return {flow: revs for flow, revs in mapping.items() if revs}


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


def analyze(
    runs: Dict[str, List[dict]],
    artifacts: Dict[str, Dict[str, Dict[str, Set[str]]]],
) -> Dict[str, object]:
    anomalies = []
    total_events = 0

    for run_id, events in runs.items():
        events.sort(key=lambda e: e.get("seq", 0))
        for event in events:
            total_events += 1
            flow = event.get("flow")
            flow_rev = event.get("flow_rev")
            step = event.get("step")
            step_id = event.get("step_id")
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
            step_meta = flow_map.get(flow_rev)
            if step_meta is None:
                anomalies.append({
                    "run_id": run_id,
                    "reason": "REV_NOT_FOUND",
                    "flow": flow,
                    "flow_rev": flow_rev,
                    "step": step,
                })
                continue
            step_ids = step_meta.get("step_ids", set())
            step_names = step_meta.get("names", set())
            if isinstance(step_id, str) and step_id not in step_ids:
                anomalies.append({
                    "run_id": run_id,
                    "reason": "STEP_ID_NOT_FOUND",
                    "flow": flow,
                    "flow_rev": flow_rev,
                    "step": step,
                    "step_id": step_id,
                })
                continue
            if step not in step_names and not step_ids:
                anomalies.append({
                    "run_id": run_id,
                    "reason": "STEP_NOT_FOUND",
                    "flow": flow,
                    "flow_rev": flow_rev,
                    "step": step,
                })
            elif step not in step_names and isinstance(step_id, str) and step_id in step_ids:
                # Step id matched but name differs – note the discrepancy
                anomalies.append({
                    "run_id": run_id,
                    "reason": "STEP_NAME_MISMATCH",
                    "flow": flow,
                    "flow_rev": flow_rev,
                    "step": step,
                    "step_id": step_id,
                })
                continue
            elif step not in step_names:
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
