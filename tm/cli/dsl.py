from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable, Sequence

from tm.dsl.lint import LintIssue, lint_paths

_DSL_EXTENSIONS = (".wdl", ".pdl")


def register_dsl_commands(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("dsl", help="Workflow/Policy DSL tooling")
    parser.set_defaults(func=_dsl_default)
    dsl_subparsers = parser.add_subparsers(dest="dsl_command")

    _register_lint(dsl_subparsers)


def _register_lint(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("lint", help="Lint DSL files for syntax issues")
    parser.add_argument("paths", nargs="+", help="Files or directories containing .wdl/.pdl files")
    parser.add_argument("--json", dest="json_output", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as errors (reserved for future use)")
    parser.set_defaults(func=_cmd_lint)


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
