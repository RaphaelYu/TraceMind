from __future__ import annotations

# from argparse import _SubParsersAction
import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from tm.utils.yaml import import_yaml

from tm.composer import ComposerError, WorkflowComposer, compose_reference_workflow
from tm.verifier import verify_reference_trace

yaml = import_yaml()


def register_compose_commands(subparsers: argparse._SubParsersAction) -> None:
    compose_parser = subparsers.add_parser("compose", help="compose workflows against validated artifacts")
    compose_parser.add_argument("--intent", help="IntentSpec YAML/JSON path (compose mode)")
    compose_parser.add_argument("--policy", help="PolicySpec YAML/JSON path (compose mode)")
    compose_parser.add_argument("--catalog", help="Capability catalog (YAML/JSON) path")
    compose_parser.add_argument(
        "--modes",
        default="conservative,aggressive",
        help="Comma-separated modes to rank candidates (default: conservative,aggressive)",
    )
    compose_parser.add_argument("--k", type=int, default=1, help="Top candidates per mode")
    compose_parser.add_argument("--explain", action="store_true", help="emit explainable reasoning for compose")
    compose_parser.add_argument("--explain-output", help="write explanation JSON to this file")
    compose_parser.set_defaults(func=_cmd_compose)
    compose_sub = compose_parser.add_subparsers(dest="compose_cmd")

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


def _load_raw(path: Path) -> Any:
    content = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        if yaml is None:
            raise RuntimeError("PyYAML is required to read YAML files")
        return yaml.safe_load(content)
    return json.loads(content)


def _load_structured(path: Path) -> Mapping[str, Any]:
    payload = _load_raw(path)
    if not isinstance(payload, Mapping):
        raise ValueError(f"{path}: expected mapping document")
    return payload


def _load_catalog_specs(path: Path) -> list[Mapping[str, Any]]:
    payload = _load_raw(path)
    if isinstance(payload, Mapping):
        return [spec for spec in payload.values() if isinstance(spec, Mapping)]
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        return [spec for spec in payload if isinstance(spec, Mapping)]
    raise ValueError(f"{path}: catalog must be mapping or list of capability specs")


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


def _cmd_compose(args: argparse.Namespace) -> int:
    if not args.intent or not args.policy or not args.catalog:
        print("compose: --intent, --policy, and --catalog are required", file=sys.stderr)
        raise SystemExit(1)
    try:
        intent = _load_structured(Path(args.intent))
        policy = _load_structured(Path(args.policy))
        catalog_specs = _load_catalog_specs(Path(args.catalog))
    except Exception as exc:
        print(f"compose: failed to load inputs: {exc}", file=sys.stderr)
        raise SystemExit(1)
    modes = [mode.strip() for mode in (args.modes or "").split(",") if mode.strip()]
    if not modes:
        modes = ["conservative", "aggressive"]
    composer = WorkflowComposer(
        intent=intent,
        policy=policy,
        capabilities=catalog_specs,
        intent_ref=args.intent,
        policy_ref=args.policy,
        catalog_ref=args.catalog,
    )
    try:
        result = composer.compose(modes, top_k=args.k or 1)
    except Exception as exc:
        print(f"compose: {exc}", file=sys.stderr)
        raise SystemExit(1)
    workflow_policy = result.get("workflow_policy") or {}
    if not workflow_policy:
        print("compose: no acceptable candidate produced", file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps(workflow_policy, indent=2, ensure_ascii=False))
    if args.explain:
        explanation = result.get("explanation", {})
        explain_text = json.dumps(explanation, indent=2, ensure_ascii=False)
        if args.explain_output:
            Path(args.explain_output).write_text(explain_text, encoding="utf-8")
        else:
            print(explain_text)
    return 0
