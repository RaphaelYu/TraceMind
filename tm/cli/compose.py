from __future__ import annotations

# from argparse import _SubParsersAction
import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

try:
    import yaml  # type: ignore[import-untyped]
except ModuleNotFoundError:
    yaml = None

from tm.composer import ComposerError, compose_reference_workflow
from tm.verifier import verify_reference_trace


def register_compose_commands(subparsers: argparse._SubParsersAction) -> None:
    compose_parser = subparsers.add_parser("compose", help="compose workflows against validated artifacts")
    compose_sub = compose_parser.add_subparsers(dest="compose_cmd", required=True)

    reference_parser = compose_sub.add_parser("reference", help="compose/verify the reference workflow")
    reference_parser.add_argument("--intent", required=True, help="IntentSpec YAML/JSON path")
    reference_parser.add_argument("--policy", required=True, help="PolicySpec YAML/JSON path")
    reference_parser.add_argument(
        "--capabilities",
        nargs="+",
        required=True,
        help="Paths to CapabilitySpec YAML/JSON files (must cover compute/validate/external)",
    )
    reference_parser.add_argument(
        "--events",
        nargs="+",
        help="Event sequence to run through the verifier (e.g. compute.process.done validate.result.passed)",
    )
    reference_parser.add_argument(
        "--format",
        choices=["json"],
        default="json",
        help="Output format for the composed workflow/report (default: json)",
    )
    reference_parser.set_defaults(func=_cmd_compose_reference)


def _load_structured(path: Path) -> Mapping[str, Any]:
    content = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        if yaml is None:
            raise RuntimeError("PyYAML is required to read YAML files")
        payload = yaml.safe_load(content)
    else:
        payload = json.loads(content)
    if not isinstance(payload, Mapping):
        raise ValueError(f"{path}: expected mapping document")
    return payload


def _cmd_compose_reference(args: argparse.Namespace) -> None:
    try:
        intent = _load_structured(Path(args.intent))
        policy = _load_structured(Path(args.policy))
        capabilities = [_load_structured(Path(cap)) for cap in args.capabilities]
    except Exception as exc:
        print(f"compose reference: {exc}", file=sys.stderr)
        raise SystemExit(1)

    try:
        workflow = compose_reference_workflow(intent, policy=policy, capabilities=capabilities)
    except ComposerError as exc:
        print(f"compose reference: {exc}", file=sys.stderr)
        raise SystemExit(1)

    output = {"workflow": workflow}

    events = list(args.events or [])
    if events:
        report = verify_reference_trace(events, workflow=workflow, policy=policy)
        output["verification"] = report

    print(json.dumps(output, indent=2, ensure_ascii=False))
