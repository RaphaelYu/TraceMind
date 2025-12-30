from __future__ import annotations

from argparse import _SubParsersAction
import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

from tm.utils.yaml import import_yaml

from tm.composer import ComposerError, compose_reference_workflow
from tm.iteration.loop import run_iteration
from tm.verifier import verify_reference_trace

yaml = import_yaml()


def register_iterate_commands(subparsers: _SubParsersAction) -> None:
    iterate_parser = subparsers.add_parser("iterate", help="run the iteration loop")
    iterate_sub = iterate_parser.add_subparsers(dest="iterate_cmd", required=True)

    reference_parser = iterate_sub.add_parser("reference", help="iteration loop for reference workflow")
    reference_parser.add_argument("--intent", required=True, help="path to IntentSpec")
    reference_parser.add_argument("--policy", required=True, help="path to PolicySpec")
    reference_parser.add_argument(
        "--capabilities", nargs="+", required=True, help="paths to CapabilitySpec files (complete set)"
    )
    reference_parser.add_argument("--events", nargs="+", required=True, help="event sequence to verify")
    reference_parser.add_argument("--format", choices=["json"], default="json", help="output format (default: json)")
    reference_parser.set_defaults(func=_cmd_iterate_reference)


def _load_structured(path: Path) -> Mapping[str, Any]:
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        if yaml is None:
            raise RuntimeError("PyYAML required for YAML files")
        payload = yaml.safe_load(text)
    else:
        payload = json.loads(text)
    if not isinstance(payload, Mapping):
        raise ValueError(f"{path}: expected mapping document")
    return payload


def _cmd_iterate_reference(args: argparse.Namespace) -> None:
    try:
        intent = _load_structured(Path(args.intent))
        policy = _load_structured(Path(args.policy))
        capabilities = [_load_structured(Path(cap)) for cap in args.capabilities]
    except Exception as exc:
        print(f"iterate reference: {exc}", file=sys.stderr)
        raise SystemExit(1)

    try:
        workflow = compose_reference_workflow(intent, policy=policy, capabilities=capabilities)
    except ComposerError as exc:
        print(f"iterate reference: {exc}", file=sys.stderr)
        raise SystemExit(1)

    report = verify_reference_trace(args.events, workflow=workflow, policy=policy)
    output = {
        "workflow": workflow,
        "verification": report,
    }
    if report["status"] == "violated":
        patch = report["metadata"].get("patch_proposal")
        if not patch:
            print("No patch proposal generated for violation", file=sys.stderr)
            raise SystemExit(1)
        iteration = run_iteration(policy, patch_proposal=patch)
        new_workflow = compose_reference_workflow(intent, policy=iteration.policy, capabilities=capabilities)
        new_report = verify_reference_trace(args.events, workflow=new_workflow, policy=iteration.policy)
        output["iteration"] = {
            "approval": iteration.approval,
            "policy": iteration.policy,
            "workflow": new_workflow,
            "verification": new_report,
        }
    print(json.dumps(output, indent=2, ensure_ascii=False))
