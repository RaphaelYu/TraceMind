from __future__ import annotations

import glob
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from tm.validate import find_conflicts


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
    try:
        import yaml  # type: ignore[import-untyped]
    except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
        raise SystemExit("PyYAML required; install with `pip install pyyaml`.") from exc
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
        if not isinstance(data, Mapping):
            raise SystemExit(f"{path}: expected mapping document")
        return data


def cmd_validate(args) -> int:
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


def register_validate_command(parent) -> None:
    validate_parser = parent.add_parser("validate", help="validate flows and policies for conflicts")
    validate_parser.add_argument("--flows", nargs="+", required=True, help="flow file paths/globs")
    validate_parser.add_argument("--policies", nargs="+", required=True, help="policy file paths/globs")
    validate_parser.add_argument("--json", action="store_true", help="emit JSON output")
    validate_parser.set_defaults(func=cmd_validate)
