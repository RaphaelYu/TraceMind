from __future__ import annotations

import glob
import json
from pathlib import Path
from typing import Mapping

try:  # pragma: no cover - optional dependency
    import yaml
except ModuleNotFoundError:  # pragma: no cover
    yaml = None

from tm.validate.simulator import simulate


def _expand(pattern: str) -> Path:
    path = Path(pattern)
    if path.exists():
        return path.resolve()
    matches = [Path(p) for p in glob.glob(pattern, recursive=True)]
    if not matches:
        raise SystemExit(f"no files matched '{pattern}'")
    return matches[0].resolve()


def _load_yaml(path: Path) -> Mapping[str, object]:
    if yaml is None:
        raise SystemExit("PyYAML required; install with `pip install pyyaml`.")
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
        if not isinstance(data, Mapping):
            raise SystemExit(f"{path}: expected mapping document")
        return data


def cmd_simulate_run(args) -> int:
    flow_path = _expand(args.flow)
    flow_doc = _load_yaml(flow_path)
    report = simulate(
        flow_doc,
        at=args.at,
        seed=args.seed,
        max_concurrency=args.max_concurrency,
    )
    if args.json:
        print(json.dumps({"flow": str(flow_path), "report": report}, indent=2, sort_keys=True))
    else:
        status = "ok" if report.get("deadlocks", 0) == 0 else "deadlock"
        print(f"{flow_path}: {status}")
        print(f"  finished steps: {report.get('finished', 0)}")
        print(f"  deadlocks: {report.get('deadlocks', 0)}")
    return 1 if report.get("deadlocks", 0) else 0


def register_simulate_command(parent) -> None:
    simulate_parser = parent.add_parser("simulate", help="simulate execution scenarios")
    simulate_sub = simulate_parser.add_subparsers(dest="simulate_cmd")

    run_cmd = simulate_sub.add_parser("run", help="simulate a flow")
    run_cmd.add_argument("--flow", required=True, help="flow file path or glob")
    run_cmd.add_argument("--policy", help="policy file path (reserved for future use)")
    run_cmd.add_argument("--at", help="simulation start timestamp (ISO8601)")
    run_cmd.add_argument("--seed", type=int, help="random seed for deterministic ordering")
    run_cmd.add_argument("--max-concurrency", type=int, default=1, help="maximum steps to run concurrently")
    run_cmd.add_argument("--json", action="store_true", help="emit JSON output")
    run_cmd.set_defaults(func=cmd_simulate_run)
