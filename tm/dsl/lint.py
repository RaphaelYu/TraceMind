from __future__ import annotations

from dataclasses import dataclass, field
import re
from collections import deque
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence, Set, Tuple

from .ir import (
    SourceSpan,
    WdlCallStep,
    WdlStep,
    WdlWhenStep,
    WdlWorkflow,
    build_pdl_ir,
    build_wdl_ir,
)
from .parser import (
    DslParseError,
    RawMapping,
    RawNode,
    RawScalar,
    RawSequence,
    parse_pdl,
    parse_wdl,
)

_INPUT_REF_PATTERN = re.compile(r"\$input\.([A-Za-z0-9_\-]+)")
_STEP_REF_PATTERN = re.compile(r"\$step\.([A-Za-z0-9_\-]+)")
_SCALAR_REF_PATTERN = re.compile(r"\$(input|step)\.([A-Za-z0-9_\-\.]+)")

"""Static checks for TraceMind DSL documents."""


@dataclass(frozen=True)
class LintIssue:
    path: Path
    code: str
    message: str
    level: str
    line: int
    column: int
    hints: Tuple[str, ...] = ()
    related: Tuple[str, ...] = ()

    def to_json(self) -> dict[str, object]:
        payload = {
            "path": str(self.path),
            "code": self.code,
            "message": self.message,
            "level": self.level,
            "line": self.line,
            "column": self.column,
        }
        if self.hints:
            payload["hints"] = list(self.hints)
        if self.related:
            payload["related"] = list(self.related)
        return payload


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

    analyzer = _WorkflowAnalyzer(workflow=workflow, path=path)
    analyzer.run()
    return analyzer.issues


def _lint_pdl(text: str, path: Path) -> List[LintIssue]:
    try:
        document = parse_pdl(text, filename=str(path))
        build_pdl_ir(document)
    except DslParseError as err:
        return [_issue_from_parse_error(err, path)]
    return []


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


def _iter_scalar_nodes(node: RawNode) -> Iterator[RawScalar]:
    if isinstance(node, RawScalar):
        yield node
    elif isinstance(node, RawMapping):
        for entry in node.entries:
            yield from _iter_scalar_nodes(entry.value)
    elif isinstance(node, RawSequence):
        for item in node.items:
            yield from _iter_scalar_nodes(item)


def _iter_wdl_steps(steps: Sequence[WdlStep]) -> Iterator[WdlStep]:
    for step in steps:
        yield step
        if isinstance(step, WdlWhenStep):
            yield from _iter_wdl_steps(step.steps)


@dataclass
class _WorkflowAnalyzer:
    workflow: WdlWorkflow
    path: Path
    issues: List[LintIssue] = field(default_factory=list)
    adjacency: Dict[str, Set[str]] = field(default_factory=dict)
    step_locations: Dict[str, SourceSpan] = field(default_factory=dict)
    entry: Optional[str] = None
    declared_inputs: Set[str] = field(init=False)

    def __post_init__(self) -> None:
        self.declared_inputs = {inp.name for inp in self.workflow.inputs}

    def run(self) -> None:
        defined_steps: Set[str] = set()
        self._process_sequence(self.workflow.steps, defined_steps, prev_exits=set(), depth=0)
        self._validate_outputs(defined_steps)
        self._validate_reachability()
        self._validate_cycles()

    # ------------------------------------------------------------------ traversal
    def _process_sequence(
        self,
        steps: Sequence[WdlStep],
        defined_steps: Set[str],
        prev_exits: Set[str],
        depth: int,
    ) -> Set[str]:
        if not steps:
            return prev_exits
        current_exits = set(prev_exits)
        available_steps = set(defined_steps)
        for step in steps:
            if isinstance(step, WdlCallStep):
                current_exits = self._process_call(step, available_steps, current_exits)
                defined_steps.add(step.step_id)
                available_steps.add(step.step_id)
            elif isinstance(step, WdlWhenStep):
                current_exits = self._process_when(step, available_steps, current_exits, depth + 1)
            else:  # pragma: no cover - defensive for future extensions
                continue
        return current_exits

    def _process_call(
        self,
        step: WdlCallStep,
        available_steps: Set[str],
        prev_exits: Set[str],
    ) -> Set[str]:
        # Duplicate detection
        if step.step_id in self.step_locations:
            first = self.step_locations[step.step_id]
            self._add_issue(
                code="duplicate-step-id",
                message=f"Step id '{step.step_id}' already defined at line {first.line}",
                location=step.location,
            )
            # continue but avoid clobbering adjacency
        else:
            self.step_locations[step.step_id] = step.location
            self.adjacency.setdefault(step.step_id, set())
            if self.entry is None:
                self.entry = step.step_id

        # Argument validation
        for arg in step.args:
            self._check_node(arg.value, available_steps)

        # Connect edges
        next_exits: Set[str] = {step.step_id}
        for src in prev_exits:
            self.adjacency.setdefault(src, set()).add(step.step_id)

        return next_exits

    def _process_when(
        self,
        step: WdlWhenStep,
        available_steps: Set[str],
        prev_exits: Set[str],
        depth: int,
    ) -> Set[str]:
        self._check_condition(step.condition, available_steps, step.location)

        if not step.steps:
            self._add_issue(
                code="empty-branch",
                message="Conditional block has no steps",
                location=step.location,
                level="warning",
            )
            return prev_exits

        branch_defined = set(available_steps)
        branch_exits = self._process_sequence(step.steps, branch_defined, prev_exits=set(), depth=depth)

        # Link previous exits to branch entry
        branch_entry = self._first_step_id(step.steps)
        if branch_entry:
            if self.entry is None and not prev_exits:
                self.entry = branch_entry
            for src in prev_exits:
                self.adjacency.setdefault(src, set()).add(branch_entry)

        # Ensure branch steps are recorded even if no entry yet
        if branch_entry is None:
            branch_entry = next(iter(branch_exits), None)
            if branch_entry and self.entry is None and not prev_exits:
                self.entry = branch_entry

        # Branch-defined steps should not escape to parent scope
        return set(prev_exits) | set(branch_exits)

    def _validate_outputs(self, available_steps: Set[str]) -> None:
        # Outputs may reference inputs or steps that are guaranteed to run.
        for output in self.workflow.outputs:
            self._check_node(output.value, available_steps)

    def _validate_reachability(self) -> None:
        if not self.step_locations:
            if self.workflow.steps:
                # steps may contain only when blocks with no call steps
                self._add_issue(
                    code="no-call-steps",
                    message="Workflow does not define any executable steps",
                    location=self.workflow.location,
                )
            return
        if self.entry is None:
            # Choose first defined step if adjacency is empty (should not happen)
            self.entry = next(iter(self.step_locations.keys()))

        visited: Set[str] = set()
        queue: deque[str] = deque()
        queue.append(self.entry)
        while queue:
            node = queue.popleft()
            if node in visited:
                continue
            visited.add(node)
            for succ in self.adjacency.get(node, ()):
                queue.append(succ)

        unreachable = set(self.step_locations.keys()) - visited
        for step_id in sorted(unreachable):
            loc = self.step_locations[step_id]
            self._add_issue(
                code="unreachable-step",
                message=f"Step '{step_id}' is not reachable from the workflow entry",
                location=loc,
            )

    def _validate_cycles(self) -> None:
        visited: Set[str] = set()
        stack: Set[str] = set()

        def dfs(node: str) -> bool:
            if node in stack:
                return True
            if node in visited:
                return False
            visited.add(node)
            stack.add(node)
            for succ in self.adjacency.get(node, ()):
                if dfs(succ):
                    self._add_issue(
                        code="cycle-detected",
                        message=f"Cycle detected involving step '{succ}'",
                        location=self.step_locations.get(succ, self.workflow.location),
                    )
                    stack.remove(node)
                    return True
            stack.remove(node)
            return False

        for node in self.step_locations:
            if dfs(node):
                break

    # ------------------------------------------------------------------ helpers
    def _check_node(self, node: RawNode, available_steps: Set[str]) -> None:
        for scalar in _iter_scalar_nodes(node):
            self._check_scalar(scalar, available_steps)

    def _check_scalar(self, scalar: RawScalar, available_steps: Set[str]) -> None:

        for match in _INPUT_REF_PATTERN.finditer(scalar.value):
            name = match.group(1)
            if name not in self.declared_inputs:
                column = scalar.location.column + match.start()
                self._add_issue(
                    code="missing-input",
                    message=f"Input '{name}' is not declared",
                    line=scalar.location.line,
                    column=column,
                )
        for match in _STEP_REF_PATTERN.finditer(scalar.value):
            name = match.group(1)
            if name not in available_steps:
                column = scalar.location.column + match.start()
                self._add_issue(
                    code="unknown-step-ref",
                    message=f"Step '{name}' is not defined or not available in this scope",
                    line=scalar.location.line,
                    column=column,
                )

    def _check_condition(self, condition: str, available_steps: Set[str], location: SourceSpan) -> None:
        for match in _SCALAR_REF_PATTERN.finditer(condition):
            ref_type, payload = match.groups()
            column = location.column + match.start()
            if ref_type == "input":
                name = payload.split(".", 1)[0]
                if name not in self.declared_inputs:
                    self._add_issue(
                        code="missing-input",
                        message=f"Input '{name}' is not declared",
                        line=location.line,
                        column=column,
                    )
            else:
                name = payload.split(".", 1)[0]
                if name not in available_steps:
                    self._add_issue(
                        code="unknown-step-ref",
                        message=f"Step '{name}' is not defined or not available in this scope",
                        line=location.line,
                        column=column,
                    )

    def _first_step_id(self, steps: Sequence[WdlStep]) -> Optional[str]:
        for step in steps:
            if isinstance(step, WdlCallStep):
                return step.step_id
            if isinstance(step, WdlWhenStep):
                nested = self._first_step_id(step.steps)
                if nested:
                    return nested
        return None

    def _add_issue(
        self,
        *,
        code: str,
        message: str,
        location: Optional[SourceSpan] = None,
        level: str = "error",
        line: Optional[int] = None,
        column: Optional[int] = None,
    ) -> None:
        default_line = self.workflow.location.line
        default_column = self.workflow.location.column
        if location is not None:
            default_line = location.line
            default_column = location.column

        self.issues.append(
            LintIssue(
                path=self.path,
                code=code,
                message=message,
                level=level,
                line=line if line is not None else default_line,
                column=column if column is not None else default_column,
            )
        )


__all__ = ["LintIssue", "lint_path", "lint_paths"]
