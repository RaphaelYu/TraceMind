from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Mapping, Sequence

from tm.controllers.cycle import (
    ControllerCycle,
    ControllerCycleError,
    ControllerCycleResult,
    write_gap_and_backlog,
)
from tm.utils.yaml import import_yaml

yaml = import_yaml()


def _write_report(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if yaml is not None:
        with path.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(payload, handle, sort_keys=True, allow_unicode=True)
        return
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _build_report_payload(
    result: ControllerCycleResult | None,
    *,
    mode: str,
    success: bool,
    dry_run: bool,
    errors: Sequence[str],
    gap_map: Path | None,
    backlog: Path | None,
) -> Mapping[str, object]:
    payload: dict[str, object] = {
        "mode": mode,
        "success": success,
        "dry_run": dry_run,
        "generated_at": datetime.now().isoformat(),
        "errors": list(errors),
    }
    if gap_map is not None:
        payload["gap_map"] = str(gap_map)
    if backlog is not None:
        payload["backlog"] = str(backlog)
    if result is None:
        return payload
    payload.update(
        {
            "bundle_artifact_id": result.bundle_artifact_id,
            "env_snapshot": result.env_snapshot.envelope.artifact_id,
            "proposed_change_plan": result.planned_change.envelope.artifact_id,
            "execution_report": result.execution_report.envelope.artifact_id,
            "start_time": result.start_time.isoformat(),
            "end_time": result.end_time.isoformat(),
            "duration_seconds": (result.end_time - result.start_time).total_seconds(),
            "policy_decisions": [
                {
                    "effect": decision.effect_name,
                    "target": decision.target,
                    "allowed": decision.allowed,
                    "reason": decision.reason,
                }
                for decision in result.policy_decisions
            ],
        }
    )
    return payload


def _cmd_controller_cycle(args: argparse.Namespace) -> int:
    bundle = Path(args.bundle)
    report_path = Path(args.report)
    runner = ControllerCycle(
        bundle_path=bundle,
        mode=args.mode,
        dry_run=args.dry_run,
        report_path=report_path,
        record_path=args.record_path,
        artifact_output_dir=report_path.parent / "controller_artifacts",
        approval_token=args.approval_token,
    )
    gap_path: Path | None = None
    backlog_path: Path | None = None
    errors: list[str] = []
    result: ControllerCycleResult | None = None
    try:
        result = runner.run()
    except ControllerCycleError as exc:
        errors = exc.errors
        dependency_id = runner.bundle_artifact_id or bundle.name
        gap_path, backlog_path = write_gap_and_backlog(report_path, dependency_id, errors)
        payload = _build_report_payload(
            result=None,
            mode=args.mode,
            success=False,
            dry_run=args.dry_run,
            errors=errors,
            gap_map=gap_path,
            backlog=backlog_path,
        )
        _write_report(report_path, payload)
        print(f"controller cycle: failed; report -> {report_path}", file=sys.stderr)
        if gap_path or backlog_path:
            print(f"gap_map -> {gap_path}; backlog -> {backlog_path}", file=sys.stderr)
        return 1
    else:
        payload = _build_report_payload(
            result=result,
            mode=args.mode,
            success=True,
            dry_run=args.dry_run,
            errors=errors,
            gap_map=None,
            backlog=None,
        )
        _write_report(report_path, payload)
        print(f"controller cycle: success; report -> {report_path}")
        return 0


def register_controller_commands(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("controller", help="controller tooling")
    sub = parser.add_subparsers(dest="controller_cmd")
    cycle_parser = sub.add_parser("cycle", help="run a single controller cycle")
    cycle_parser.add_argument("--bundle", required=True, help="path to accepted agent bundle artifact")
    cycle_parser.add_argument("--report", required=True, help="path to write controller cycle report")
    cycle_parser.add_argument("--mode", choices=["live", "replay"], default="live", help="decide agent mode")
    cycle_parser.add_argument("--dry-run", action="store_true", help="skip registry updates")
    cycle_parser.add_argument(
        "--record-path",
        default=".tracemind/controller_decide_records.json",
        help="path to store recorded decide plans",
    )
    cycle_parser.add_argument(
        "--approval-token",
        default="approved",
        help="token indicating the run was approved (used when resource effects exist)",
    )
    cycle_parser.set_defaults(func=_cmd_controller_cycle)
