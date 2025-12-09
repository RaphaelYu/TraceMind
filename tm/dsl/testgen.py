from __future__ import annotations

from dataclasses import dataclass, replace
import ast
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, Mapping

from ._render import render_raw_node
from .ir import (
    PdlArm,
    PdlAssignment,
    PdlChoose,
    PdlConditional,
    PdlPolicy,
    PdlStatement,
    WdlStep,
    WdlWhenStep,
    WdlWorkflow,
    build_pdl_ir,
    build_wdl_ir,
)
from .parser import DslParseError, parse_pdl, parse_wdl

"""
Test generation utilities for the TraceMind DSL suite.

Transforms WDL/PDL documents into deterministic fixtures that can be replayed
via ``tm validate``/``tm simulate``.  Each case captures the input payload and
an optional expectation stub, leaving downstream tooling to execute the flow
or policy under test.
"""

_DEFAULT_MIN_CASES = 6


class TestGenError(RuntimeError):
    """Raised when fixture generation fails."""


@dataclass(frozen=True)
class GeneratedCase:
    name: str
    inputs: Dict[str, object]
    expectations: Dict[str, object]


@dataclass(frozen=True)
class TestGenResult:
    source: Path
    kind: str  # "wdl" | "pdl"
    cases: Tuple[GeneratedCase, ...]
    output_dir: Path


def generate_for_path(
    path: Path,
    *,
    max_cases: Optional[int] = None,
    output_dir: Optional[Path] = None,
) -> TestGenResult:
    """
    Generate test fixtures for a single DSL document.
    """
    suffix = path.suffix.lower()
    if suffix == ".wdl":
        try:
            workflow = build_wdl_ir(parse_wdl(path.read_text(encoding="utf-8"), filename=str(path)))
        except DslParseError as exc:
            raise TestGenError(str(exc)) from exc
        cases = _generate_wdl_cases(workflow)
        kind = "wdl"
        source_name = workflow.name
    elif suffix == ".pdl":
        try:
            policy = build_pdl_ir(parse_pdl(path.read_text(encoding="utf-8"), filename=str(path)))
        except DslParseError as exc:
            raise TestGenError(str(exc)) from exc
        cases = _generate_pdl_cases(policy, path.stem)
        kind = "pdl"
        source_name = path.stem
    else:
        raise TestGenError(f"Unsupported file extension for test generation: {suffix}")

    if max_cases is not None:
        cases = cases[:max_cases]
    if not cases:
        raise TestGenError("No test cases could be generated for this document")

    fixtures_root = output_dir or (path.parent / "fixtures")
    target_dir = fixtures_root / path.stem
    target_dir.mkdir(parents=True, exist_ok=True)
    _write_cases(target_dir, source_name, kind, cases)
    return TestGenResult(source=path, kind=kind, cases=tuple(cases), output_dir=target_dir)


def discover_inputs(paths: Sequence[Path]) -> List[Path]:
    """
    Collect WDL/PDL files from the provided paths.
    """
    seen: Dict[Path, None] = {}
    for candidate in paths:
        if candidate.is_file():
            if candidate.suffix.lower() in {".wdl", ".pdl"}:
                seen.setdefault(candidate.resolve(), None)
        elif candidate.is_dir():
            for nested in candidate.rglob("*"):
                if nested.is_file() and nested.suffix.lower() in {".wdl", ".pdl"}:
                    seen.setdefault(nested.resolve(), None)
    return sorted(seen.keys())


# --------------------------------------------------------------------------- WDL generation


def _generate_wdl_cases(workflow: WdlWorkflow) -> List[GeneratedCase]:
    base_inputs = {inp.name: _sample_for_type(inp.type_name) for inp in workflow.inputs}
    cases: List[GeneratedCase] = []
    seen: set[Tuple[Tuple[str, object], ...]] = set()

    def add_case(name: str, inputs: Dict[str, object]) -> None:
        frozen = tuple(sorted(inputs.items()))
        if frozen in seen:
            return
        seen.add(frozen)
        cases.append(GeneratedCase(name=name, inputs=dict(inputs), expectations={}))

    add_case("base", base_inputs)

    for step in _iter_steps(workflow.steps):
        if isinstance(step, WdlWhenStep):
            for case_name, values in _cases_from_condition(step.condition, base_inputs):
                add_case(case_name, values)

    for name, value in base_inputs.items():
        add_case(f"{name}_none", {**base_inputs, name: None})
        if isinstance(value, list):
            add_case(f"{name}_empty", {**base_inputs, name: []})
        elif isinstance(value, str):
            add_case(f"{name}_blank", {**base_inputs, name: ""})
        elif isinstance(value, bool):
            add_case(f"{name}_toggle", {**base_inputs, name: not value})

    cases = _ensure_min_cases(cases, base_inputs, prefix="auto")
    return cases


def _iter_steps(steps: Sequence[WdlStep]) -> Iterable[WdlStep]:
    for step in steps:
        yield step
        if isinstance(step, WdlWhenStep):
            yield from _iter_steps(step.steps)


def _cases_from_condition(condition: str, base_inputs: Dict[str, object]) -> List[Tuple[str, Dict[str, object]]]:
    condition = condition.strip()
    cases: List[Tuple[str, Dict[str, object]]] = []

    if condition.startswith("$input.") and " in " in condition:
        field, _, remainder = condition.partition(" in ")
        field_name = field[len("$input.") :]
        try:
            options = ast.literal_eval(remainder.strip())
        except Exception:
            options = []
        if isinstance(options, (list, tuple)):
            for value in options:
                cases.append((f"{field_name}_is_{_slug(str(value))}", {**base_inputs, field_name: value}))
            if options:
                cases.append((f"{field_name}_else", {**base_inputs, field_name: _fallback_non_match(options)}))
        return cases

    comparison = _match_comparison(condition)
    if comparison:
        field_name, op, literal = comparison
        literal_value = _parse_literal(literal)
        if isinstance(literal_value, (int, float)):
            below, above = _adjust_numeric(literal_value)
            cases.append((f"{field_name}_{op}_{literal_value}", {**base_inputs, field_name: literal_value}))
            cases.append((f"{field_name}_below", {**base_inputs, field_name: below}))
            cases.append((f"{field_name}_above", {**base_inputs, field_name: above}))
        elif isinstance(literal_value, str):
            cases.append((f"{field_name}_eq", {**base_inputs, field_name: literal_value}))
            cases.append((f"{field_name}_neq", {**base_inputs, field_name: literal_value + "_alt"}))
        return cases

    return cases


# --------------------------------------------------------------------------- PDL generation


def _generate_pdl_cases(policy: PdlPolicy, policy_name: str) -> List[GeneratedCase]:
    value_keys = _collect_policy_value_keys(policy)
    thresholds = _collect_thresholds(policy.arms)

    base_values = {key: 0 for key in sorted(value_keys)}
    cases: List[GeneratedCase] = []
    seen: set[Tuple[Tuple[str, object], ...]] = set()

    def add_case(name: str, values: Mapping[str, object]) -> None:
        frozen = tuple(sorted(values.items()))
        if frozen in seen:
            return
        seen.add(frozen)
        inputs: Dict[str, object] = {"values": dict(values)}
        cases.append(GeneratedCase(name=name, inputs=inputs, expectations={}))

    add_case("base", base_values or {"metric": 0})

    for key, threshold in thresholds.items():
        base_values.setdefault(key, 0)
        below, above = _adjust_numeric(threshold)
        add_case(f"{key}_below_threshold", {**base_values, key: below})
        add_case(f"{key}_at_threshold", {**base_values, key: threshold})
        add_case(f"{key}_above_threshold", {**base_values, key: above})

    if not thresholds and not value_keys:
        add_case("generic_violation", {"metric": 1})
        add_case("generic_ok", {"metric": 0})

    normalized_cases: List[GeneratedCase] = []
    for case in cases:
        inputs_obj = case.inputs.get("values", case.inputs) if isinstance(case.inputs, dict) else case.inputs
        inputs_dict: Dict[str, object] = dict(inputs_obj) if isinstance(inputs_obj, Mapping) else {"values": inputs_obj}
        normalized_cases.append(replace(case, inputs=inputs_dict))

    cases = _ensure_min_cases(
        normalized_cases,
        dict(base_values or {"metric": 0}),
        prefix="policy",
    )

    wrapped: List[GeneratedCase] = []
    for case in cases:
        inputs = case.inputs if isinstance(case.inputs, dict) else {"values": case.inputs}
        if "values" not in inputs:
            inputs = {"values": inputs}
        wrapped.append(GeneratedCase(case.name, dict(inputs), case.expectations))
    return wrapped


def _collect_policy_value_keys(policy: PdlPolicy) -> set[str]:
    keys: set[str] = set()

    def visit(statement: PdlStatement) -> None:
        if isinstance(statement, PdlAssignment):
            keys.update(_extract_value_keys(statement.expression))
        elif isinstance(statement, PdlConditional):
            keys.update(_extract_value_keys(statement.condition))
            for child in statement.body:
                visit(child)
            if statement.else_body:
                for child in statement.else_body:
                    visit(child)
        elif isinstance(statement, PdlChoose):
            for option in statement.options:
                keys.update(_extract_value_keys(option.expression))

    for stmt in policy.evaluate:
        visit(stmt)
    return keys


def _collect_thresholds(arms: Sequence[PdlArm]) -> Dict[str, float]:
    thresholds: Dict[str, float] = {}
    for arm in arms:
        for field in arm.fields:
            if "threshold" in field.name.lower():
                value = render_raw_node(field.value)
                if isinstance(value, (int, float)):
                    thresholds[field.name] = float(value)
    return thresholds


def _extract_value_keys(expression: str) -> set[str]:
    keys: set[str] = set()
    parts = expression.split("values[")
    for part in parts[1:]:
        if part.startswith(('"', "'")):
            quote = part[0]
            end = part.find(quote, 1)
            if end > 1:
                keys.add(part[1:end])
    return keys


# --------------------------------------------------------------------------- shared helpers


def _sample_for_type(type_name: str) -> object:
    normalized = (type_name or "").lower()
    if "list" in normalized or normalized.startswith("[]"):
        return ["item1", "item2"]
    if "bool" in normalized:
        return True
    if "int" in normalized:
        return 1
    if any(token in normalized for token in ("float", "double", "decimal")):
        return 1.0
    if "string" in normalized or "str" in normalized:
        return "sample"
    return "sample"


def _match_comparison(condition: str) -> Optional[Tuple[str, str, str]]:
    for op in (">=", "<=", "==", "!=", ">", "<"):
        if op in condition:
            left, _, right = condition.partition(op)
            left = left.strip()
            right = right.strip()
            if left.startswith("$input."):
                return left[len("$input.") :], op, right
    return None


def _parse_literal(text: str) -> object:
    try:
        return ast.literal_eval(text)
    except Exception:
        return text.strip()


def _adjust_numeric(value: float) -> Tuple[float, float]:
    if isinstance(value, int):
        return value - 1, value + 1
    delta = max(abs(value) * 0.1, 0.5)
    return value - delta, value + delta


def _fallback_non_match(options: Sequence[object]) -> object:
    if not options:
        return "other"
    first = options[0]
    if isinstance(first, str):
        candidate = first + "_other"
        return candidate if candidate not in options else first + "_alt"
    if isinstance(first, bool):
        return not first
    if isinstance(first, (int, float)):
        candidate_num = first + 1
        return candidate_num if candidate_num not in options else first - 1
    return "other"


def _ensure_min_cases(
    cases: List[GeneratedCase],
    base_inputs: Dict[str, object],
    *,
    prefix: str,
) -> List[GeneratedCase]:
    if len(cases) >= _DEFAULT_MIN_CASES:
        return cases
    mutable = list(cases)
    index = 0
    while len(mutable) < _DEFAULT_MIN_CASES:
        mutable.append(GeneratedCase(name=f"{prefix}_{index}", inputs=dict(base_inputs), expectations={}))
        index += 1
    return mutable


def _slug(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in value)
    return cleaned.strip("_") or "value"


def _write_cases(target_dir: Path, source_name: str, kind: str, cases: Sequence[GeneratedCase]) -> None:
    for index, case in enumerate(cases, start=1):
        payload = {
            "name": case.name,
            "kind": kind,
            "source": source_name,
            "inputs": case.inputs,
            "expectations": case.expectations,
        }
        path = target_dir / f"case_{index:02d}.json"
        with path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)


__all__ = [
    "TestGenError",
    "GeneratedCase",
    "TestGenResult",
    "generate_for_path",
    "discover_inputs",
]
