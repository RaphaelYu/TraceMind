from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from tm.utils.yaml import import_yaml

from .intent import evaluate_intent_status
from tm.composer import WorkflowComposer
from tm.runtime.workflow_executor import execute_workflow
from tm.verifier import WorkflowVerifier

yaml = import_yaml()


def _load_structured(path: Path) -> Mapping[str, Any]:
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        if yaml is None:
            raise RuntimeError("PyYAML required for YAML artifacts")
        payload = yaml.safe_load(text)
    else:
        payload = json.loads(text)
    if not isinstance(payload, Mapping):
        raise RuntimeError(f"{path}: expected mapping document")
    return payload


def _load_catalog_specs(path: Path) -> list[Mapping[str, Any]]:
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        if yaml is None:
            raise RuntimeError("PyYAML required for YAML artifacts")
        payload = yaml.safe_load(text)
    else:
        payload = json.loads(text)
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        return [spec for spec in payload if isinstance(spec, Mapping)]
    if isinstance(payload, Mapping):
        return [spec for spec in payload.values() if isinstance(spec, Mapping)]
    raise RuntimeError(f"{path}: catalog must be mapping or list of capability specs")


def _parse_guard_decisions(values: Iterable[str] | None) -> dict[str, bool]:
    decisions: dict[str, bool] = {}
    for raw in values or []:
        if "=" not in raw:
            continue
        name, value = raw.split("=", 1)
        decisions[name.strip()] = value.strip().lower() in {"1", "true", "yes", "on"}
    return decisions


def rerun_pipeline(
    intent_path: Path,
    policy_path: Path,
    catalog_path: Path,
    *,
    mode: str,
    guard_decisions: Mapping[str, bool] | None = None,
    events: Sequence[str] | None = None,
) -> Mapping[str, Any]:
    intent = _load_structured(intent_path)
    policy = _load_structured(policy_path)
    capabilities = _load_catalog_specs(catalog_path)

    status, reason, details = evaluate_intent_status(intent, policy, capabilities)
    intent_result: dict[str, Any] = {"status": status}
    if reason:
        intent_result["reason"] = reason
    if details:
        intent_result["details"] = details
    if status != "OK":
        raise RuntimeError(f"intent validation failed: {status} {reason}")

    composer = WorkflowComposer(
        intent=intent,
        policy=policy,
        capabilities=capabilities,
        intent_ref=str(intent_path),
        policy_ref=str(policy_path),
        catalog_ref=str(catalog_path),
    )
    compose_result = composer.compose([mode], top_k=1)
    workflow_policy = compose_result.get("workflow_policy") or {}
    explanation = compose_result.get("explanation", {})
    if not workflow_policy:
        raise RuntimeError("compose: no acceptable candidate")

    verifier = WorkflowVerifier(policy=policy, capabilities=capabilities)
    verification = verifier.verify(workflow_policy)
    if not verification.success:
        raise RuntimeError(f"verification failed: {verification.counterexample}")

    trace = execute_workflow(
        workflow_policy,
        policy=policy,
        capabilities=capabilities,
        guard_decisions=guard_decisions or {},
        events=events or [],
    )

    return {
        "intent": intent_result,
        "compose": {"workflow": workflow_policy, "explanation": explanation},
        "verification": {"success": True},
        "trace": trace,
    }


def register_rerun_command(subparsers: argparse._SubParsersAction) -> None:
    rerun_parser = subparsers.add_parser("rerun", help="compose/verify/run from explicit artifacts")
    rerun_parser.add_argument("--intent", required=True, help="IntentSpec path")
    rerun_parser.add_argument("--policy", required=True, help="PolicySpec path")
    rerun_parser.add_argument("--catalog", required=True, help="Capability catalog path")
    rerun_parser.add_argument(
        "--mode",
        choices=["conservative", "aggressive"],
        default="conservative",
        help="Composer mode for rerun (default: conservative)",
    )
    rerun_parser.add_argument(
        "--guard-decision",
        action="append",
        help="Guard decision in the form name=true|false (repeatable)",
    )
    rerun_parser.add_argument(
        "--events",
        nargs="+",
        help="Additional events to append to the ExecutionTrace",
    )
    rerun_parser.add_argument("--format", choices=["json"], default="json", help="output format")
    rerun_parser.set_defaults(func=_cmd_rerun)


def _cmd_rerun(args: argparse.Namespace) -> int:
    guard_decisions = _parse_guard_decisions(args.guard_decision)
    try:
        payload = rerun_pipeline(
            intent_path=Path(args.intent),
            policy_path=Path(args.policy),
            catalog_path=Path(args.catalog),
            mode=args.mode,
            guard_decisions=guard_decisions,
            events=args.events or [],
        )
    except Exception as exc:
        print(f"rerun: {exc}", file=sys.stderr)
        raise SystemExit(1)

    if args.format == "json":
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print("rerun completed")
    return 0
