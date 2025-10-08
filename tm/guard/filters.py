"""Built-in guard filters and registry for custom hooks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

GuardHandler = Callable[["GuardRule", Sequence[Any], Mapping[str, Any]], Iterable["GuardViolation"]]

_CUSTOM_RULES: Dict[str, GuardHandler] = {}


@dataclass(eq=False)
class GuardRule:
    name: str
    path: Optional[str]
    options: Dict[str, Any]


@dataclass(frozen=True)
class GuardViolation:
    rule: str
    path: Optional[str]
    reason: str
    details: Tuple[Tuple[str, Any], ...] = ()

    def as_dict(self) -> Dict[str, Any]:
        payload = {
            "rule": self.rule,
            "reason": self.reason,
        }
        if self.path:
            payload["path"] = self.path
        if self.details:
            payload.update(dict(self.details))
        return payload


@dataclass(frozen=True)
class GuardDecision:
    allowed: bool
    violations: Tuple[GuardViolation, ...]

    @property
    def first(self) -> Optional[GuardViolation]:
        return self.violations[0] if self.violations else None


class GuardBlockedError(RuntimeError):
    def __init__(self, violation: GuardViolation) -> None:
        super().__init__(violation.reason)
        self.violation = violation


class GuardEngine:
    """Execute configured rules against input payloads."""

    def __init__(self, *, registry: Optional[Dict[str, GuardHandler]] = None) -> None:
        self._builtins = {
            "length_max": _rule_length_max,
            "required": _rule_required,
            "regex_deny": _rule_regex_deny,
            "deny_keywords": _rule_deny_keywords,
        }
        self._registry = registry or {}

    def evaluate(
        self,
        payload: Any,
        rules: Sequence[GuardRule],
        *,
        context: Optional[Mapping[str, Any]] = None,
    ) -> GuardDecision:
        ctx = dict(context or {})
        violations: List[GuardViolation] = []
        for rule in rules:
            handler = self._resolve_handler(rule.name)
            if handler is None:
                continue
            values = _extract_values(payload, rule.path)
            for violation in handler(rule, values, ctx):
                violations.append(violation)
        allowed = not violations
        return GuardDecision(allowed=allowed, violations=tuple(violations))

    def _resolve_handler(self, name: str) -> Optional[GuardHandler]:
        if name in self._registry:
            return self._registry[name]
        if name in _CUSTOM_RULES:
            return _CUSTOM_RULES[name]
        return self._builtins.get(name)

    @staticmethod
    def compile_rules(definitions: Iterable[Mapping[str, Any]]) -> Tuple[GuardRule, ...]:
        compiled: List[GuardRule] = []
        for entry in definitions:
            if not isinstance(entry, Mapping):
                continue
            raw_name = entry.get("type")
            if not isinstance(raw_name, str) or not raw_name.strip():
                continue
            path = entry.get("path")
            compiled.append(
                GuardRule(
                    name=raw_name.strip(),
                    path=str(path) if isinstance(path, str) and path else None,
                    options={k: v for k, v in entry.items() if k not in {"type", "path"}},
                )
            )
        return tuple(compiled)


def register_guard(name: str) -> Callable[[GuardHandler], GuardHandler]:
    """Register a custom guard handler available by name."""

    if not isinstance(name, str) or not name.strip():
        raise ValueError("Guard name must be a non-empty string")
    normalized = name.strip()

    def _decorator(func: GuardHandler) -> GuardHandler:
        _CUSTOM_RULES[normalized] = func
        return func

    return _decorator


# ---------------------------------------------------------------------------
# Built-in handlers
# ---------------------------------------------------------------------------


def _rule_length_max(rule: GuardRule, values: Sequence[Any], _: Mapping[str, Any]) -> Iterable[GuardViolation]:
    try:
        limit = int(rule.options.get("value"))
    except (TypeError, ValueError):
        return []
    violations: List[GuardViolation] = []
    for idx, value in enumerate(values):
        if value is None:
            continue
        text = str(value)
        if len(text) > limit:
            violations.append(
                GuardViolation(
                    rule=rule.name,
                    path=rule.path,
                    reason="length_exceeded",
                    details=(("limit", limit), ("actual", len(text)), ("index", idx)),
                )
            )
    return violations


def _rule_required(rule: GuardRule, values: Sequence[Any], _: Mapping[str, Any]) -> Iterable[GuardViolation]:
    if values:
        for value in values:
            if value not in (None, "", [], {}):
                return []
    return [
        GuardViolation(
            rule=rule.name,
            path=rule.path,
            reason="missing_required_value",
        )
    ]


def _rule_regex_deny(rule: GuardRule, values: Sequence[Any], _: Mapping[str, Any]) -> Iterable[GuardViolation]:
    pattern = rule.options.get("pattern")
    if not isinstance(pattern, str) or not pattern:
        return []
    flags = re.IGNORECASE if rule.options.get("ignore_case", True) else 0
    compiled = re.compile(pattern, flags=flags)
    violations: List[GuardViolation] = []
    for idx, value in enumerate(values):
        if not isinstance(value, str):
            continue
        if compiled.search(value):
            violations.append(
                GuardViolation(
                    rule=rule.name,
                    path=rule.path,
                    reason="regex_block",
                    details=(("pattern", pattern), ("index", idx)),
                )
            )
    return violations


def _rule_deny_keywords(rule: GuardRule, values: Sequence[Any], _: Mapping[str, Any]) -> Iterable[GuardViolation]:
    raw_list = rule.options.get("values")
    if not isinstance(raw_list, Sequence) or isinstance(raw_list, (str, bytes)):
        return []
    keywords = [str(item).lower() for item in raw_list if isinstance(item, (str, bytes))]
    if not keywords:
        return []
    violations: List[GuardViolation] = []
    for idx, value in enumerate(values):
        if not isinstance(value, str):
            continue
        lowered = value.lower()
        for needle in keywords:
            if needle in lowered:
                violations.append(
                    GuardViolation(
                        rule=rule.name,
                        path=rule.path,
                        reason="keyword_block",
                        details=(("keyword", needle), ("index", idx)),
                    )
                )
                break
    return violations


# ---------------------------------------------------------------------------
# Path resolution helpers
# ---------------------------------------------------------------------------


def _extract_values(data: Any, path: Optional[str]) -> List[Any]:
    if not path:
        return [data]
    tokens = _tokenize_path(path)
    if not tokens:
        return [data]
    current: List[Any] = [data]
    for token in tokens:
        next_values: List[Any] = []
        if token == "root":
            next_values = [data]
            current = next_values
            continue
        for value in current:
            if isinstance(value, Mapping):
                if token == "*":
                    next_values.extend(value.values())
                else:
                    if token in value:
                        next_values.append(value[token])
            elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                if token == "*":
                    next_values.extend(value)
                else:
                    idx = _try_int(token)
                    if idx is not None and 0 <= idx < len(value):
                        next_values.append(value[idx])
        current = [item for item in next_values if item is not None]
        if not current:
            break
    return current


def _tokenize_path(path: str) -> List[str]:
    cleaned = path.strip()
    if cleaned.startswith("$"):
        cleaned = cleaned[1:]
        if cleaned.startswith("."):
            cleaned = cleaned[1:]
    tokens: List[str] = []
    buffer = ""
    i = 0
    while i < len(cleaned):
        char = cleaned[i]
        if char == ".":
            if buffer:
                tokens.append(buffer)
                buffer = ""
            i += 1
        elif char == "[":
            if buffer:
                tokens.append(buffer)
                buffer = ""
            end = cleaned.find("]", i)
            if end == -1:
                break
            content = cleaned[i + 1 : end].strip()
            if content in {"*", ""}:
                tokens.append("*")
            else:
                tokens.append(content.strip("'\""))
            i = end + 1
        else:
            buffer += char
            i += 1
    if buffer:
        tokens.append(buffer)
    if not tokens:
        return []
    return [token or "*" for token in tokens]


def _try_int(value: str) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "GuardDecision",
    "GuardEngine",
    "GuardBlockedError",
    "GuardRule",
    "GuardViolation",
    "register_guard",
]
