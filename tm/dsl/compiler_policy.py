from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Sequence, Mapping

from ._render import render_raw_node
from .ir import (
    PdlArm,
    PdlAssignment,
    PdlChoose,
    PdlConditional,
    PdlEmitField,
    PdlPolicy,
    PdlStatement,
    SourceSpan,
)


class PolicyCompileError(ValueError):
    """Raised when a PDL policy cannot be compiled."""


@dataclass(frozen=True)
class PolicyCompilation:
    policy_id: str
    data: Mapping[str, object]
    source: Optional[Path]


def compile_policy(
    policy: PdlPolicy, *, source: Optional[Path] = None, policy_id: Optional[str] = None
) -> PolicyCompilation:
    resolved_policy_id = policy_id or _derive_policy_id(policy, source)
    compiled: Dict[str, object] = {
        "policy": {
            "id": resolved_policy_id,
            "strategy": policy.version,
            "params": {
                "arms": _render_arms(policy.arms),
                "epsilon": policy.epsilon,
                "evaluate": [_render_statement(stmt) for stmt in policy.evaluate],
                "emit": _render_emit(policy.emit),
            },
            "metadata": {
                "dsl": {
                    "version": policy.version,
                    "source": str(source) if source else None,
                }
            },
        }
    }
    return PolicyCompilation(policy_id=resolved_policy_id, data=compiled, source=source)


def _derive_policy_id(policy: PdlPolicy, source: Optional[Path]) -> str:
    if source is not None:
        stem = source.stem
        if stem:
            return stem
    return f"policy_{abs(hash((policy.version, len(policy.arms)))):x}"


def _render_arms(arms: Sequence[PdlArm]) -> Dict[str, Dict[str, object]]:
    rendered: Dict[str, Dict[str, object]] = {}
    for arm in arms:
        rendered[arm.name] = {field.name: render_raw_node(field.value) for field in arm.fields}
    return rendered


def _render_emit(fields: Sequence[PdlEmitField]) -> Dict[str, object]:
    return {field.name: render_raw_node(field.value) for field in fields}


def _render_statement(statement: PdlStatement) -> Dict[str, object]:
    if isinstance(statement, PdlAssignment):
        payload_assign: Dict[str, object] = {
            "type": "assignment",
            "target": statement.target,
            "operator": statement.operator,
            "expression": statement.expression,
        }
        if statement.statement_id:
            payload_assign["id"] = statement.statement_id
        payload_assign.update(_span_metadata(statement.location))
        return payload_assign
    if isinstance(statement, PdlChoose):
        payload_choose: Dict[str, object] = {
            "type": "choose",
            "options": [
                {
                    "name": option.name,
                    "expression": option.expression,
                    "probability": option.probability,
                    **_span_metadata(option.location),
                }
                for option in statement.options
            ],
        }
        payload_choose.update(_span_metadata(statement.location))
        return payload_choose
    if isinstance(statement, PdlConditional):
        payload_if: Dict[str, object] = {
            "type": "if",
            "condition": statement.condition,
            "then": [_render_statement(child) for child in statement.body],
            "else": [_render_statement(child) for child in statement.else_body] if statement.else_body else None,
        }
        payload_if.update(_span_metadata(statement.location))
        return payload_if
    raise PolicyCompileError(f"Unsupported statement type {type(statement)!r}")


def _span_metadata(span: SourceSpan) -> Dict[str, object]:
    return {
        "line": span.line,
        "column": span.column,
        "filename": str(span.filename) if span.filename else None,
    }


__all__ = ["PolicyCompilation", "PolicyCompileError", "compile_policy"]
