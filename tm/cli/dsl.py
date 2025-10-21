from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Iterable, Sequence, List, Tuple

from tm.dsl.compiler import CompileError, CompiledArtifact, compile_paths
from tm.dsl.lint import LintIssue, lint_paths
from tm.dsl.plan import PlanError, WorkflowPlan, plan_paths, plan_to_dict, plan_to_dot
from tm.dsl.testgen import TestGenError, generate_for_path, discover_inputs

_DSL_EXTENSIONS = (".wdl", ".pdl")


def register_dsl_commands(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("dsl", help="Workflow/Policy DSL tooling")
    parser.set_defaults(func=_dsl_default)
    dsl_subparsers = parser.add_subparsers(dest="dsl_command")

    _register_lint(dsl_subparsers)
    _register_compile(dsl_subparsers)
    _register_plan(dsl_subparsers)
    _register_testgen(dsl_subparsers)


def _register_lint(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("lint", help="Lint DSL files for syntax issues")
    parser.add_argument("paths", nargs="+", help="Files or directories containing .wdl/.pdl files")
    parser.add_argument("--json", dest="json_output", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as errors (reserved for future use)")
    parser.set_defaults(func=_cmd_lint)


def _register_compile(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "compile",
        help="Compile DSL files into flow/policy artifacts",
        description="Compile WDL/PDL into flow YAML and policy JSON artifacts.",
        epilog="Examples:\n  tm dsl compile examples/dsl/opcua --out out/dsl\n  tm dsl compile flow.wdl policy.pdl --json",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("paths", nargs="+", help="Files or directories containing .wdl/.pdl files")
    parser.add_argument("--out", default="out", help="Output directory for compiled artifacts (default: out/)")
    parser.add_argument("--json", dest="json_output", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument("--force", action="store_true", help="Overwrite existing artifacts")
    parser.add_argument("--no-lint", action="store_true", help="Skip linting before compilation")
    parser.add_argument("--emit-ir", action="store_true", help="Emit Flow IR artifacts and manifest.json")
    parser.add_argument(
        "--clean", action="store_true", help="Remove previously generated IR artifacts before compiling"
    )
    parser.add_argument(
        "--clean-all",
        action="store_true",
        help="Remove the entire output directory before compiling (requires --yes)",
    )
    parser.add_argument("--yes", action="store_true", help="Confirm destructive clean operations")
    parser.set_defaults(func=_cmd_compile)


def _register_plan(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "plan",
        help="Generate plan graphs for workflows",
        description="Analyze WDL workflows and export plan graphs as DOT/JSON.",
        epilog="Examples:\n  tm dsl plan flow.wdl --dot out/flow.dot\n  tm dsl plan flows/ --json out/plans",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("paths", nargs="+", help="Files or directories containing .wdl workflows")
    parser.add_argument(
        "--dot",
        dest="dot_path",
        help="Write Graphviz DOT output to this file or directory (directory required for multiple workflows)",
    )
    parser.add_argument(
        "--json",
        dest="json_path",
        help="Write plan JSON output to this file or directory (directory required for multiple workflows)",
    )
    parser.set_defaults(func=_cmd_plan)


def _register_testgen(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "testgen",
        help="Generate fixtures from DSL workflows/policies",
        description="Produce test cases (inputs + expectations) for WDL/PDL documents.",
        epilog="Examples:\n  tm dsl testgen examples/dsl/opcua --out examples/fixtures\n  tm dsl testgen flow.wdl --max-cases 10",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("paths", nargs="+", help="Files or directories containing .wdl/.pdl files")
    parser.add_argument("--out", default="examples/fixtures", help="Output directory for generated fixtures")
    parser.add_argument("--max-cases", type=int, help="Maximum number of cases per document")
    parser.add_argument("--json", dest="json_output", action="store_true", help="Emit summary as JSON")
    parser.set_defaults(func=_cmd_testgen)


def _dsl_default(args: argparse.Namespace) -> None:
    if getattr(args, "dsl_command", None) is None:
        print("Usage: tm dsl <command> [options]", file=sys.stderr)
        sys.exit(1)


def _cmd_lint(args: argparse.Namespace) -> None:
    paths = list(_resolve_paths([Path(p) for p in args.paths]))
    if not paths:
        print("No DSL files found", file=sys.stderr)
        sys.exit(1)
    issues = lint_paths(paths)
    if args.json_output:
        _print_json(issues)
    else:
        _print_text(issues)
    exit_code = 1 if any(issue.level == "error" for issue in issues) else 0
    sys.exit(exit_code)


def _cmd_compile(args: argparse.Namespace) -> None:
    candidate_paths = [Path(p) for p in args.paths]
    out_dir = Path(args.out)
    if args.clean_all:
        if not args.yes:
            print("--clean-all requires --yes confirmation", file=sys.stderr)
            sys.exit(1)
        _rm_tree(out_dir)
    elif args.clean:
        _clean_ir_outputs(out_dir)

    try:
        artifacts = compile_paths(
            candidate_paths,
            out_dir=out_dir,
            force=args.force,
            run_lint=not args.no_lint,
            emit_ir=args.emit_ir,
        )
    except CompileError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    if args.json_output:
        _print_compile_json(artifacts)
    else:
        _print_compile_text(artifacts, out_dir)


def _rm_tree(path: Path) -> None:
    try:
        if path.exists():
            shutil.rmtree(path)
    except OSError as exc:
        print(f"Failed to remove {path}: {exc}", file=sys.stderr)
        sys.exit(1)


def _clean_ir_outputs(out_dir: Path) -> None:
    flows_dir = out_dir / "flows"
    if flows_dir.exists():
        for ir_path in flows_dir.glob("*.ir.json"):
            try:
                ir_path.unlink()
            except OSError as exc:
                print(f"Failed to remove {ir_path}: {exc}", file=sys.stderr)
                sys.exit(1)
    manifest_path = out_dir / "manifest.json"
    if manifest_path.exists():
        try:
            manifest_path.unlink()
        except OSError as exc:
            print(f"Failed to remove {manifest_path}: {exc}", file=sys.stderr)
            sys.exit(1)
    cache_dir = out_dir / ".ir-cache"
    if cache_dir.exists():
        try:
            shutil.rmtree(cache_dir)
        except OSError as exc:
            print(f"Failed to remove {cache_dir}: {exc}", file=sys.stderr)
            sys.exit(1)


def _cmd_plan(args: argparse.Namespace) -> None:
    candidate_paths = [Path(p) for p in args.paths]
    try:
        plans = plan_paths(candidate_paths)
    except PlanError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    _print_plan_summary(plans)
    if args.dot_path:
        try:
            _write_plan_outputs(plans, Path(args.dot_path), ".dot", plan_to_dot)
        except PlanError as exc:
            print(str(exc), file=sys.stderr)
            sys.exit(1)
    if args.json_path:
        try:
            _write_plan_outputs(
                plans,
                Path(args.json_path),
                ".json",
                lambda plan: json.dumps(plan_to_dict(plan), indent=2),
            )
        except PlanError as exc:
            print(str(exc), file=sys.stderr)
            sys.exit(1)


def _cmd_testgen(args: argparse.Namespace) -> None:
    candidates = discover_inputs([Path(p) for p in args.paths])
    if not candidates:
        print("No DSL files found", file=sys.stderr)
        sys.exit(1)
    out_dir = Path(args.out)
    errors: List[str] = []
    results = []
    for path in candidates:
        try:
            result = generate_for_path(path, max_cases=args.max_cases, output_dir=out_dir)
            results.append(result)
        except TestGenError as exc:
            errors.append(f"{path}: {exc}")
    if errors:
        for line in errors:
            print(line, file=sys.stderr)
        sys.exit(1)
    _print_testgen_summary(results, json_output=args.json_output)


def _print_compile_text(artifacts: List[CompiledArtifact], out_dir: Path) -> None:
    if not artifacts:
        print("No artifacts generated")
        return
    print(f"Wrote artifacts to {out_dir.resolve()}:")
    for artifact in artifacts:
        print(f"  [{artifact.kind}] {artifact.output}")


def _print_compile_json(artifacts: List[CompiledArtifact]) -> None:
    data = [
        {
            "source": str(artifact.source),
            "kind": artifact.kind,
            "id": artifact.identifier,
            "output": str(artifact.output),
        }
        for artifact in artifacts
    ]
    json.dump({"artifacts": data}, sys.stdout, indent=2)
    sys.stdout.write("\n")


def _print_plan_summary(plans: List[Tuple[Path, WorkflowPlan]]) -> None:
    for source, plan in plans:
        print(f"{source}: entry={plan.entry or 'unknown'}, nodes={len(plan.nodes)}, edges={len(plan.edges)}")


def _write_plan_outputs(
    plans: List[Tuple[Path, WorkflowPlan]],
    destination: Path,
    extension: str,
    formatter,
) -> None:
    paths = _resolve_output_targets(plans, destination, extension)
    for (source, plan), output_path in zip(plans, paths):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        data = formatter(plan)
        with output_path.open("w", encoding="utf-8") as fh:
            fh.write(data if isinstance(data, str) else str(data))


def _resolve_output_targets(
    plans: List[Tuple[Path, WorkflowPlan]],
    destination: Path,
    extension: str,
) -> List[Path]:
    if len(plans) == 1 and destination.suffix:
        destination.parent.mkdir(parents=True, exist_ok=True)
        return [destination]
    if destination.suffix:
        raise PlanError("Multiple workflows require a directory output for plan artifacts")
    destination.mkdir(parents=True, exist_ok=True)
    targets: List[Path] = []
    for _, plan in plans:
        targets.append(destination / f"{plan.name}{extension}")
    return targets


def _print_testgen_summary(results, json_output: bool) -> None:
    if json_output:
        payload = [
            {
                "source": str(result.source),
                "kind": result.kind,
                "cases": len(result.cases),
                "output_dir": str(result.output_dir),
            }
            for result in results
        ]
        json.dump({"fixtures": payload}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return
    for result in results:
        print(
            f"{result.source}: generated {len(result.cases)} case(s) -> {result.output_dir}"  # pragma: no cover - CLI output
        )


def _resolve_paths(candidates: Sequence[Path]) -> Iterable[Path]:
    seen: dict[Path, None] = {}
    for candidate in candidates:
        if candidate.is_file():
            seen.setdefault(candidate.resolve(), None)
        elif candidate.is_dir():
            for nested in sorted(candidate.rglob("*")):
                if nested.is_file() and nested.suffix.lower() in _DSL_EXTENSIONS:
                    seen.setdefault(nested.resolve(), None)
        else:
            continue
    return seen.keys()


def _print_text(issues: Sequence[LintIssue]) -> None:
    if not issues:
        print("No issues found")
        return
    for issue in issues:
        location = f"{issue.line}:{issue.column}" if issue.line else "-"
        print(f"{issue.path}:{location}: {issue.level.upper()} {issue.code} {issue.message}")


def _print_json(issues: Sequence[LintIssue]) -> None:
    data = {
        "issues": [issue.to_json() for issue in issues],
        "summary": {
            "errors": sum(1 for issue in issues if issue.level == "error"),
            "warnings": sum(1 for issue in issues if issue.level != "error"),
        },
    }
    json.dump(data, sys.stdout, indent=2)
    sys.stdout.write("\n")


__all__ = ["register_dsl_commands"]
