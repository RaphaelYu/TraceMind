from __future__ import annotations

import glob
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence
import sys

from tm.artifacts import (
    ArtifactValidationError,
    validate_capability_spec,
    validate_execution_trace,
    validate_integrated_state_report,
    validate_intent_spec,
    validate_patch_proposal,
    validate_policy_spec,
    validate_workflow_policy,
)
from tm.utils.yaml import import_yaml
from tm.validate import find_conflicts

yaml = import_yaml()


def _expand(patterns: Sequence[str]) -> Sequence[Path]:
    seen: dict[Path, None] = {}
    for pattern in patterns:
        path = Path(pattern)
        matches: Iterable[Path]
        if path.exists():
            matches = [path]
        else:
            matches = (Path(p) for p in glob.glob(pattern, recursive=True))
        found = False
        for match in matches:
            if match.is_file():
                seen.setdefault(match.resolve(), None)
                found = True
        if not found:
            raise SystemExit(f"no files matched '{pattern}'")
    return tuple(sorted(seen.keys()))


def _load_yaml(path: Path) -> Mapping[str, object]:
    if yaml is None:
        raise SystemExit("PyYAML required; install with `pip install pyyaml`.")
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
        if not isinstance(data, Mapping):
            raise SystemExit(f"{path}: expected mapping document")
        return data


def _load_structured(path: Path) -> Mapping[str, object]:
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        if yaml is None:
            raise ValueError("PyYAML required; install with `pip install pyyaml`.")
        data = yaml.safe_load(text) or {}
    else:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON: {exc}") from exc
    if not isinstance(data, Mapping):
        raise ValueError(f"{path}: expected mapping document")
    return data


ARTIFACT_VALIDATORS = {
    "IntentSpec": validate_intent_spec,
    "PolicySpec": validate_policy_spec,
    "CapabilitySpec": validate_capability_spec,
    "WorkflowPolicy": validate_workflow_policy,
    "ExecutionTrace": validate_execution_trace,
    "IntegratedStateReport": validate_integrated_state_report,
    "PatchProposal": validate_patch_proposal,
}


def _infer_artifact_schema(payload: Mapping[str, object]) -> str:
    if "proposal_id" in payload:
        return "PatchProposal"
    if "trace_id" in payload:
        return "ExecutionTrace"
    if "report_id" in payload:
        return "IntegratedStateReport"
    if "workflow_id" in payload and "steps" in payload:
        return "WorkflowPolicy"
    if "capability_id" in payload and "event_types" in payload:
        return "CapabilitySpec"
    if "policy_id" in payload and "state_schema" in payload:
        return "PolicySpec"
    if "intent_id" in payload and "goal" in payload:
        return "IntentSpec"
    raise RuntimeError("unable to infer artifact schema")


def _validate_artifact_file(path: Path, schema_name: str | None) -> None:
    payload = _load_structured(path)
    if schema_name is None:
        schema_name = _infer_artifact_schema(payload)
    if schema_name not in ARTIFACT_VALIDATORS:
        raise RuntimeError(f"unknown schema '{schema_name}'")
    validator = ARTIFACT_VALIDATORS[schema_name]
    validator(payload)


def _validate_artifacts(paths: Sequence[str], schema_name: str | None) -> bool:
    artifact_paths = _expand(paths)
    has_errors = False
    for artifact_path in artifact_paths:
        try:
            _validate_artifact_file(artifact_path, schema_name)
            print(f"{artifact_path}: valid")
        except (ArtifactValidationError, RuntimeError, ValueError) as exc:
            print(f"{artifact_path}: {exc}", file=sys.stderr)
            has_errors = True
    return has_errors


def _validate_conflicts(args) -> int:
    if not args.flows or not args.policies:
        raise SystemExit("--flows and --policies are required to run conflict validation")
    flow_paths = _expand(args.flows)
    policy_paths = _expand(args.policies)
    flows = [_load_yaml(path) for path in flow_paths]
    policies = [_load_yaml(path) for path in policy_paths]
    conflicts = find_conflicts(flows, policies)
    if args.json:
        payload = {
            "flows": [str(path) for path in flow_paths],
            "policies": [str(path) for path in policy_paths],
            "conflicts": [conflict.__dict__ for conflict in conflicts],
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        if not conflicts:
            print("no conflicts detected")
        for conflict in conflicts:
            subjects = ", ".join(conflict.subjects)
            print(f"[{conflict.kind}] {conflict.detail} :: {subjects}")
    return 1 if conflicts else 0


def cmd_validate(args) -> int:
    exit_code = 0
    handled = False

    if args.flows or args.policies:
        handled = True
        exit_code = _validate_conflicts(args) or exit_code

    if args.artifacts:
        handled = True
        schema_name = args.schema
        errors = _validate_artifacts(args.artifacts, schema_name)
        if errors:
            exit_code = 1

    if not handled:
        raise SystemExit("validate: supply --flows/--policies or artifact file paths")

    return exit_code


def register_validate_command(parent) -> None:
    validate_parser = parent.add_parser(
        "validate",
        help="validate flows/policies for conflicts or artifacts for schema conformance",
    )
    validate_parser.add_argument("--flows", nargs="+", help="flow file paths/globs")
    validate_parser.add_argument("--policies", nargs="+", help="policy file paths/globs")
    validate_parser.add_argument(
        "--json",
        action="store_true",
        help="emit JSON output for conflicts (only used when flows/policies provided)",
    )
    validate_parser.add_argument(
        "--schema",
        choices=sorted(ARTIFACT_VALIDATORS),
        help="explicit artifact schema to validate files against",
    )
    validate_parser.add_argument(
        "artifacts",
        nargs="*",
        help="artifact files (YAML/JSON) to validate (Intent/Policy/Capability/...)",
    )
    validate_parser.set_defaults(func=cmd_validate)
