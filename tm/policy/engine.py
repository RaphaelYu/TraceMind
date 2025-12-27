from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence
import re


@dataclass(frozen=True)
class PolicyViolation:
    rule_id: str
    kind: str
    detail: str
    evidence: Mapping[str, Any] | None = None

    def to_dict(self) -> Mapping[str, Any]:
        payload: dict[str, Any] = {
            "rule_id": self.rule_id,
            "kind": self.kind,
            "detail": self.detail,
        }
        if self.evidence is not None:
            payload["evidence"] = dict(self.evidence)
        return payload


@dataclass(frozen=True)
class PolicyEvaluationResult:
    violations: tuple[PolicyViolation, ...]

    @property
    def succeeded(self) -> bool:
        return not self.violations

    def to_list(self) -> list[Mapping[str, Any]]:
        return [violation.to_dict() for violation in self.violations]


class PolicyEvaluator:
    def __init__(self, spec: Mapping[str, Any]):
        self.spec = spec
        self.state_schema = spec.get("state_schema", {}) or {}
        self._invariants = tuple(spec.get("invariants") or [])
        self._guards = tuple(spec.get("guards") or [])

    def check_state(self, state: Mapping[str, Any]) -> PolicyEvaluationResult:
        violations: list[PolicyViolation] = []
        for invariant in self._invariants:
            inv_type = invariant.get("type")
            if inv_type != "never":
                continue
            rule_id = str(invariant.get("id") or invariant.get("rule_id") or invariant.get("name") or "unknown")
            condition = str(invariant.get("condition") or "").strip()
            if not condition:
                continue
            if self._matches_condition(condition, state):
                violations.append(
                    PolicyViolation(
                        rule_id=rule_id,
                        kind="invariant",
                        detail=str(invariant.get("description") or f"never {condition}"),
                        evidence={
                            "state_key": condition,
                            "value": state.get(condition),
                        },
                    )
                )
        return PolicyEvaluationResult(tuple(violations))

    def evaluate_guard(
        self, capability_id: str, guard_decisions: Mapping[str, bool] | None = None
    ) -> PolicyEvaluationResult:
        guard_decisions = guard_decisions or {}
        violations: list[PolicyViolation] = []
        for guard in self._guards:
            required_for = guard.get("required_for")
            if not self._guard_applies(required_for, capability_id):
                continue
            rule_id = str(guard.get("name") or guard.get("id") or "guard")
            satisfied = bool(guard_decisions.get(rule_id))
            if not satisfied:
                violations.append(
                    PolicyViolation(
                        rule_id=rule_id,
                        kind="guard",
                        detail=f"guard '{rule_id}' unsatisfied for {capability_id}",
                        evidence={"guard": guard, "capability_id": capability_id},
                    )
                )
        return PolicyEvaluationResult(tuple(violations))

    def check_trace(
        self,
        trace: Mapping[str, Any],
        *,
        guard_decisions: Mapping[str, bool] | None = None,
        event: Mapping[str, Any] | None = None,
    ) -> PolicyEvaluationResult:
        state = trace.get("state_snapshot") or trace.get("state") or {}
        violation_set = list(self.check_state(state).violations)
        capability_id = trace.get("capability_id")
        if event and not capability_id:
            capability_id = str(event.get("capability_id") or event.get("capability") or "")
        if capability_id:
            violation_set.extend(self.evaluate_guard(capability_id, guard_decisions).violations)
        return PolicyEvaluationResult(tuple(violation_set))

    @staticmethod
    def _guard_applies(required_for: Any, capability_id: str) -> bool:
        if required_for is None:
            return False
        if isinstance(required_for, str):
            return required_for == capability_id
        if isinstance(required_for, Sequence):
            return any(str(entry) == capability_id for entry in required_for)
        return False

    @staticmethod
    def _matches_condition(condition: str, state: Mapping[str, Any]) -> bool:
        normalized = condition.strip()
        if not normalized:
            return False
        try:
            tokens = _tokenize_condition(normalized)
            parser = _ConditionParser(tokens, state)
            result = parser.parse_expression()
            if parser.peek() is not None:
                raise ValueError("unexpected tokens")
            return result
        except ValueError:
            return False


def _tokenize_condition(condition: str) -> list[str]:
    tokens: list[str] = []
    idx = 0
    length = len(condition)
    while idx < length:
        char = condition[idx]
        if char.isspace():
            idx += 1
            continue
        if condition.startswith("&&", idx):
            tokens.append("AND")
            idx += 2
            continue
        if condition.startswith("||", idx):
            tokens.append("OR")
            idx += 2
            continue
        if char == "!":
            tokens.append("NOT")
            idx += 1
            continue
        if char in {"(", ")"}:
            tokens.append(char)
            idx += 1
            continue
        match = re.match(r"[A-Za-z0-9_.]+", condition[idx:])
        if match:
            token = match.group(0)
            tokens.append(token)
            idx += len(token)
            continue
        raise ValueError(f"invalid character in condition: '{char}'")
    return tokens


class _ConditionParser:
    def __init__(self, tokens: list[str], state: Mapping[str, Any]) -> None:
        self.tokens = tokens
        self.state = state
        self.position = 0

    def peek(self) -> str | None:
        if self.position < len(self.tokens):
            return self.tokens[self.position]
        return None

    def consume(self) -> str | None:
        token = self.peek()
        if token is not None:
            self.position += 1
        return token

    def parse_expression(self) -> bool:
        value = self._parse_term()
        while self.peek() == "OR":
            self.consume()
            value = value or self._parse_term()
        return value

    def _parse_term(self) -> bool:
        value = self._parse_factor()
        while self.peek() == "AND":
            self.consume()
            value = value and self._parse_factor()
        return value

    def _parse_factor(self) -> bool:
        token = self.peek()
        if token is None:
            raise ValueError("unexpected end of condition")
        if token == "NOT":
            self.consume()
            return not self._parse_factor()
        if token == "(":
            self.consume()
            value = self.parse_expression()
            closing = self.consume()
            if closing != ")":
                raise ValueError("missing closing parenthesis")
            return value
        self.consume()
        lower = token.lower()
        if lower == "true":
            return True
        if lower == "false":
            return False
        state_value: Any = self.state.get(token)
        if state_value is None and token.endswith(".unvalidated"):
            prefix = token[: -len(".unvalidated")]
            validated_key = f"{prefix}.validated"
            state_value = not bool(self.state.get(validated_key))
        return bool(state_value)


__all__ = ["PolicyViolation", "PolicyEvaluationResult", "PolicyEvaluator"]
