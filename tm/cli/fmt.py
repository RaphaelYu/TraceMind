from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path
from typing import Iterable

from tm.utils.yaml import import_yaml

yaml = import_yaml()


def _expand(patterns: Iterable[str]) -> tuple[Path, ...]:
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


def _ensure_trailing_newline(text: str) -> str:
    return text if text.endswith("\n") else f"{text}\n"


def _format_json(original: str) -> str:
    try:
        payload = json.loads(original)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid JSON: {exc}") from exc
    formatted = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)
    return _ensure_trailing_newline(formatted)


def _format_yaml(original: str) -> str:
    if yaml is None:
        raise RuntimeError("PyYAML required; install with `pip install pyyaml`")
    payload = yaml.safe_load(original)
    formatted = yaml.safe_dump(
        payload or {},
        sort_keys=True,
        allow_unicode=True,
        default_flow_style=False,
    )
    return _ensure_trailing_newline(formatted)


def _format_file(path: Path) -> None:
    original = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        formatted = _format_yaml(original)
    else:
        formatted = _format_json(original)
    if formatted != original:
        path.write_text(formatted, encoding="utf-8")
        print(f"{path}: formatted")
    else:
        print(f"{path}: already formatted")


def _cmd_fmt(args: argparse.Namespace) -> int:
    try:
        targets = _expand(args.paths)
    except SystemExit as exc:
        print(str(exc), file=sys.stderr)
        return 1
    success = True
    for target in targets:
        try:
            _format_file(target)
        except Exception as exc:
            print(f"{target}: {exc}", file=sys.stderr)
            success = False
    return 0 if success else 1


def register_fmt_command(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "fmt",
        help="format artifact files (JSON/YAML)",
        description="Rewrite artifact files with consistent indentation and sorted keys.",
    )
    parser.add_argument("paths", nargs="+", help="file paths or glob patterns")
    parser.set_defaults(func=_cmd_fmt)
