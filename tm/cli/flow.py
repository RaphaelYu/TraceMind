from __future__ import annotations

import glob
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Mapping, Sequence, Tuple

from tm.ana import IssueLevel, PlanResult, PlanStats, ValidationIssue, plan, validate


@dataclass(frozen=True)
class Thresholds:
    max_depth_warn: int | None = None
    max_depth_error: int | None = None
    max_nodes_warn: int | None = None
    max_nodes_error: int | None = None
    max_out_degree_warn: int | None = None
    max_out_degree_error: int | None = None


@dataclass
class FlowAnalysis:
    path: Path
    graph: Dict[str, Tuple[str, ...]]
    plan_result: PlanResult | None
    max_out_degree: int
    validation_issues: Tuple[ValidationIssue, ...]
    threshold_issues: Tuple[Dict[str, object], ...]


_ENV_MAP = {
    "max_depth_warn": "TM_FLOW_WARN_MAX_DEPTH",
    "max_depth_error": "TM_FLOW_ERROR_MAX_DEPTH",
    "max_nodes_warn": "TM_FLOW_WARN_MAX_NODES",
    "max_nodes_error": "TM_FLOW_ERROR_MAX_NODES",
    "max_out_degree_warn": "TM_FLOW_WARN_MAX_OUT_DEGREE",
    "max_out_degree_error": "TM_FLOW_ERROR_MAX_OUT_DEGREE",
}


def _load_thresholds_from_env() -> Thresholds:
    values: Dict[str, int | None] = {}
    for field_name, env_name in _ENV_MAP.items():
        raw = os.getenv(env_name)
        if raw is None or raw == "":
            values[field_name] = None
            continue
        try:
            values[field_name] = int(raw)
        except ValueError:
            raise SystemExit(f"invalid integer for {env_name}: {raw!r}")
    return Thresholds(**values)  # type: ignore[arg-type]


def _expand_patterns(patterns: Sequence[str]) -> Tuple[Path, ...]:
    seen: Dict[Path, None] = {}
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


def _load_graph_from_file(path: Path) -> Dict[str, Tuple[str, ...]]:
    try:
        import yaml  # type: ignore[import-untyped]
    except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
        raise SystemExit("PyYAML is required for flow commands; install with `pip install pyyaml`.") from exc
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    steps = data.get("steps")
    if not isinstance(steps, Mapping):
        raise SystemExit(f"{path}: expected 'steps' mapping in flow definition")
    graph: Dict[str, Tuple[str, ...]] = {}
    for raw_id, spec in steps.items():
        node_id = str(raw_id)
        successors: Iterable[str] = ()
        if isinstance(spec, Mapping):
            raw_next = spec.get("next", [])
            if raw_next is None:
                successors = ()
            elif isinstance(raw_next, str):
                successors = (raw_next,)
            elif isinstance(raw_next, Iterable):
                successors = tuple(str(item) for item in raw_next)
            else:
                raise SystemExit(f"{path}: step '{node_id}' has invalid 'next' field")
        elif spec is None:
            successors = ()
        else:
            raise SystemExit(f"{path}: step '{node_id}' must be mapping or null")
        deduped: Dict[str, None] = {}
        for succ in successors:
            succ_id = str(succ)
            deduped.setdefault(succ_id, None)
        graph[node_id] = tuple(deduped.keys())
    return graph


def _check_thresholds(stats: PlanStats, max_out_degree: int, thresholds: Thresholds) -> Tuple[Dict[str, object], ...]:
    issues: list[Dict[str, object]] = []

    def _check(value: int, warn: int | None, error: int | None, code: str, label: str) -> None:
        if error is not None and value > error:
            issues.append(
                {
                    "level": IssueLevel.ERROR,
                    "code": code + "_error",
                    "message": f"{label} {value} exceeds error threshold {error}",
                }
            )
        elif warn is not None and value > warn:
            issues.append(
                {
                    "level": IssueLevel.WARNING,
                    "code": code + "_warn",
                    "message": f"{label} {value} exceeds warning threshold {warn}",
                }
            )

    _check(stats.depth, thresholds.max_depth_warn, thresholds.max_depth_error, "max_depth", "depth")
    _check(stats.nodes, thresholds.max_nodes_warn, thresholds.max_nodes_error, "max_nodes", "node count")
    _check(
        max_out_degree, thresholds.max_out_degree_warn, thresholds.max_out_degree_error, "max_out_degree", "out-degree"
    )

    issues.sort(
        key=lambda issue: (
            0 if issue["level"] == IssueLevel.ERROR else 1,
            issue["code"],
        )
    )
    return tuple(issues)


def _analyze_flow(path: Path, thresholds: Thresholds) -> FlowAnalysis:
    graph = _load_graph_from_file(path)
    report = validate(graph)
    plan_result: PlanResult | None = None
    threshold_issues: Tuple[Dict[str, object], ...] = ()

    max_out_degree = max((len(targets) for targets in graph.values()), default=0)
    if not report.has_errors():
        try:
            plan_result = plan(graph)
            if plan_result:
                threshold_issues = _check_thresholds(plan_result.stats, max_out_degree, thresholds)
        except ValueError as exc:
            # cycle detected by planner; add as error when validator missed
            threshold_issues = threshold_issues + (
                {
                    "level": IssueLevel.ERROR,
                    "code": "plan_failed",
                    "message": str(exc),
                },
            )
    return FlowAnalysis(
        path=path,
        graph=graph,
        plan_result=plan_result,
        max_out_degree=max_out_degree,
        validation_issues=report.issues,
        threshold_issues=threshold_issues,
    )


def _issue_dict(issue) -> Dict[str, object]:
    if isinstance(issue, dict):
        payload = issue.copy()
        payload["level"] = issue["level"].value  # type: ignore[index]
        return payload
    return {
        "level": issue.level.value,
        "code": issue.code,
        "message": issue.message,
        **({"node": issue.node} if getattr(issue, "node", None) else {}),
    }


def cmd_flow_lint(args) -> int:
    thresholds = _load_thresholds_from_env()
    files = _expand_patterns(args.paths)
    exit_code = 0
    for path in files:
        analysis = _analyze_flow(path, thresholds)
        status = "ok"
        has_validation_errors = any(issue.level == IssueLevel.ERROR for issue in analysis.validation_issues)
        has_threshold_errors = any(issue["level"] == IssueLevel.ERROR for issue in analysis.threshold_issues)
        has_warnings = bool(analysis.validation_issues or analysis.threshold_issues)
        if has_validation_errors or has_threshold_errors:
            exit_code = 1
            status = "error"
        elif has_warnings:
            status = "warn"

        print(f"{path}: {status}")
        for issue in analysis.validation_issues:
            print(f"  - [{issue.level.value}] {issue.code}: {issue.message}", end="")
            if issue.node:
                print(f" (node={issue.node})")
            else:
                print()
        for issue in analysis.threshold_issues:
            print(f"  - [{issue['level'].value}] {issue['code']}: {issue['message']}")
        if analysis.plan_result:
            stats = analysis.plan_result.stats
            print(
                f"  stats: nodes={stats.nodes} depth={stats.depth} "
                f"max_width={stats.max_width} max_out_degree={analysis.max_out_degree}"
            )
    return exit_code


def cmd_flow_plan(args) -> int:
    thresholds = _load_thresholds_from_env()
    files = _expand_patterns(args.paths)
    analyses = [_analyze_flow(path, thresholds) for path in files]

    payload = []
    exit_code = 0
    for analysis in analyses:
        issues = [_issue_dict(issue) for issue in analysis.validation_issues]
        issues.extend(_issue_dict(issue) for issue in analysis.threshold_issues)
        if any(issue["level"] == "error" for issue in issues):
            exit_code = 1
        stats_dict = None
        layers = None
        if analysis.plan_result:
            stats_dict = {
                "nodes": analysis.plan_result.stats.nodes,
                "depth": analysis.plan_result.stats.depth,
                "max_width": analysis.plan_result.stats.max_width,
                "max_out_degree": analysis.max_out_degree,
            }
            layers = [list(layer) for layer in analysis.plan_result.layers]
        payload.append(
            {
                "path": str(analysis.path),
                "issues": sorted(issues, key=lambda issue: (issue["level"], issue["code"], issue.get("node", ""))),
                "stats": stats_dict,
                "layers": layers,
            }
        )

    payload.sort(key=lambda item: item["path"])

    if args.json:
        print(json.dumps({"flows": payload}, indent=2, sort_keys=True))
    else:
        for entry in payload:
            path = entry["path"]
            issues = entry["issues"]
            stats = entry["stats"]
            status = "ok"
            if any(issue["level"] == "error" for issue in issues):
                status = "error"
            elif issues:
                status = "warn"
            print(f"{path}: {status}")
            if stats:
                print(
                    f"  stats: nodes={stats['nodes']} depth={stats['depth']} "
                    f"max_width={stats['max_width']} max_out_degree={stats['max_out_degree']}"
                )
            for issue in issues:
                suffix = f" (node={issue['node']})" if issue.get("node") else ""
                print(f"  - [{issue['level']}] {issue['code']}: {issue['message']}{suffix}")

    return exit_code


def register_flow_commands(parent) -> None:
    flow_parser = parent.add_parser("flow", help="flow analysis tools")
    flow_sub = flow_parser.add_subparsers(dest="flowcmd")

    lint = flow_sub.add_parser("lint", help="lint flow definitions for structural issues")
    lint.add_argument("paths", nargs="+", help="flow file paths or glob patterns")
    lint.set_defaults(func=cmd_flow_lint)

    plan_cmd = flow_sub.add_parser("plan", help="plan flows and report DAG statistics")
    plan_cmd.add_argument("paths", nargs="+", help="flow file paths or glob patterns")
    plan_cmd.add_argument("--json", action="store_true", help="emit JSON output")
    plan_cmd.set_defaults(func=cmd_flow_plan)
