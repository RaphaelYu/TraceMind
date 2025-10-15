from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path
from typing import Iterator, List, Sequence

from .ir import WdlCallStep, WdlStep, WdlWhenStep, WdlWorkflow, build_pdl_ir, build_wdl_ir
from .parser import DslParseError, RawMapping, RawNode, RawScalar, RawSequence, parse_pdl, parse_wdl

_INPUT_REF_PATTERN = re.compile(r"\$input\.([A-Za-z0-9_\-]+)")

"""Static checks for TraceMind DSL documents."""


@dataclass(frozen=True)
class LintIssue:
    path: Path
    code: str
    message: str
    level: str
    line: int
    column: int

    def to_json(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "code": self.code,
            "message": self.message,
            "level": self.level,
            "line": self.line,
            "column": self.column,
        }


def lint_path(path: Path) -> List[LintIssue]:
    text = path.read_text(encoding="utf-8")
    detect = _detect_kind(path, text)
    if detect == "pdl":
        return _lint_pdl(text, path)
    return _lint_wdl(text, path)


def lint_paths(paths: Sequence[Path]) -> List[LintIssue]:
    issues: List[LintIssue] = []
    for path in paths:
        try:
            issues.extend(lint_path(path))
        except OSError as exc:
            issues.append(
                LintIssue(
                    path=path,
                    code="read-error",
                    message=str(exc),
                    level="error",
                    line=0,
                    column=0,
                )
            )
    return issues


def _detect_kind(path: Path, text: str) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdl":
        return "pdl"
    if suffix == ".wdl":
        return "wdl"
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.lower().startswith("version:"):
            value = stripped.split(":", 1)[1].strip()
            if value.startswith("pdl/"):
                return "pdl"
            break
    return "wdl"


def _lint_wdl(text: str, path: Path) -> List[LintIssue]:
    try:
        document = parse_wdl(text, filename=str(path))
        workflow = build_wdl_ir(document)
    except DslParseError as err:
        return [_issue_from_parse_error(err, path)]

    issues: List[LintIssue] = []
    issues.extend(_validate_wdl_steps(workflow, path))
    issues.extend(_validate_wdl_inputs(workflow, path))
    return issues


def _lint_pdl(text: str, path: Path) -> List[LintIssue]:
    try:
        document = parse_pdl(text, filename=str(path))
        build_pdl_ir(document)
    except DslParseError as err:
        return [_issue_from_parse_error(err, path)]
    return []


def _validate_wdl_steps(workflow: WdlWorkflow, path: Path) -> List[LintIssue]:
    issues: List[LintIssue] = []
    seen: dict[str, SourcePosition] = {}
    for step in _iter_wdl_steps(workflow.steps):
        if isinstance(step, WdlCallStep):
            if step.step_id in seen:
                first = seen[step.step_id]
                issues.append(
                    LintIssue(
                        path=path,
                        code="duplicate-step-id",
                        message=f"Step id '{step.step_id}' already defined at line {first.line}",
                        level="error",
                        line=step.location.line,
                        column=step.location.column,
                    )
                )
            else:
                seen[step.step_id] = SourcePosition(step.location.line, step.location.column)
    return issues


def _validate_wdl_inputs(workflow: WdlWorkflow, path: Path) -> List[LintIssue]:
    declared = {inp.name for inp in workflow.inputs}
    issues: List[LintIssue] = []

    def _check_node(node: RawNode) -> None:
        for scalar in _iter_scalar_nodes(node):
            for match in _INPUT_REF_PATTERN.finditer(scalar.value):
                name = match.group(1)
                if name not in declared:
                    column = scalar.location.column + match.start()
                    issues.append(
                        LintIssue(
                            path=path,
                            code="missing-input",
                            message=f"Input '{name}' is not declared",
                            level="error",
                            line=scalar.location.line,
                            column=column,
                        )
                    )

    for step in _iter_wdl_steps(workflow.steps):
        if isinstance(step, WdlCallStep):
            for arg in step.args:
                _check_node(arg.value)
        elif isinstance(step, WdlWhenStep):
            continue

    for output in workflow.outputs:
        _check_node(output.value)
    return issues


def _iter_wdl_steps(steps: Sequence[WdlStep]) -> Iterator[WdlStep]:
    for step in steps:
        yield step
        if isinstance(step, WdlWhenStep):
            yield from _iter_wdl_steps(step.steps)


def _iter_scalar_nodes(node: RawNode) -> Iterator[RawScalar]:
    if isinstance(node, RawScalar):
        yield node
    elif isinstance(node, RawMapping):
        for entry in node.entries:
            yield from _iter_scalar_nodes(entry.value)
    elif isinstance(node, RawSequence):
        for item in node.items:
            yield from _iter_scalar_nodes(item)


def _issue_from_parse_error(err: DslParseError, path: Path) -> LintIssue:
    line = 0
    column = 0
    if err.location:
        line = err.location.line
        column = err.location.column
    return LintIssue(
        path=path,
        code="parse-error",
        message=err.message,
        level="error",
        line=line,
        column=column,
    )


@dataclass(frozen=True)
class SourcePosition:
    line: int
    column: int


__all__ = ["LintIssue", "lint_path", "lint_paths"]
