from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, List, Mapping, MutableSequence, Sequence, Union

_TRIGGER_PATTERN = re.compile(r"^[A-Za-z0-9_\.\[\]\*\$]+$")


@dataclass
class LintIssue:
    code: str
    message: str
    severity: str
    path: str | None = None


def _iter_steps(plan_body: Union[Mapping[str, Any], Any]) -> MutableSequence[Mapping[str, Any]]:
    raw_steps = plan_body.get("steps") if isinstance(plan_body, Mapping) else getattr(plan_body, "steps", [])
    if raw_steps is None:
        return []
    if not isinstance(raw_steps, Sequence) or isinstance(raw_steps, (str, bytes, bytearray)):
        return []
    return list(raw_steps)


def _iter_rules(plan_body: Union[Mapping[str, Any], Any]) -> MutableSequence[Mapping[str, Any]]:
    raw_rules = plan_body.get("rules") if isinstance(plan_body, Mapping) else getattr(plan_body, "rules", [])
    if raw_rules is None:
        return []
    if not isinstance(raw_rules, Sequence) or isinstance(raw_rules, (str, bytes, bytearray)):
        return []
    return list(raw_rules)


def lint_plan(plan_body: Union[Mapping[str, Any], Any]) -> List[LintIssue]:
    issues: List[LintIssue] = []
    steps = _iter_steps(plan_body)
    seen_names: set[str] = set()
    for idx, raw_step in enumerate(steps):
        path = f"steps[{idx}]"
        name = raw_step.get("name")
        if not isinstance(name, str) or not name.strip():
            issues.append(
                LintIssue(code="STEP_NAME", message="step.name must be a non-empty string", severity="error", path=path)
            )
        else:
            if name in seen_names:
                issues.append(
                    LintIssue(
                        code="STEP_NAME_UNIQUE",
                        message=f"step '{name}' is not unique",
                        severity="error",
                        path=path,
                    )
                )
            seen_names.add(name)
        for field in ("reads", "writes"):
            if field not in raw_step:
                issues.append(
                    LintIssue(
                        code="STEP_IO",
                        message=f"step '{name or path}' missing '{field}' field",
                        severity="error",
                        path=f"{path}.{field}",
                    )
                )
            else:
                value = raw_step[field]
                if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
                    issues.append(
                        LintIssue(
                            code="STEP_IO",
                            message=f"step '{name or path}' {field} must be a list",
                            severity="error",
                            path=f"{path}.{field}",
                        )
                    )
    rules = _iter_rules(plan_body)
    for ridx, raw_rule in enumerate(rules):
        path = f"rules[{ridx}]"
        rule_name = raw_rule.get("name") or f"rule[{ridx}]"
        steps_ref = raw_rule.get("steps")
        if not steps_ref:
            issues.append(
                LintIssue(
                    code="RULE_STEPS",
                    message=f"rule '{rule_name}' must reference steps",
                    severity="error",
                    path=path,
                )
            )
        else:
            if not isinstance(steps_ref, Sequence) or isinstance(steps_ref, (str, bytes, bytearray)):
                issues.append(
                    LintIssue(
                        code="RULE_STEPS",
                        message=f"rule '{rule_name}' steps must be a list",
                        severity="error",
                        path=f"{path}.steps",
                    )
                )
            else:
                for ref in steps_ref:
                    if ref not in seen_names:
                        issues.append(
                            LintIssue(
                                code="RULE_REF",
                                message=f"rule '{rule_name}' references undefined step '{ref}'",
                                severity="error",
                                path=f"{path}.steps",
                            )
                        )
        triggers = raw_rule.get("triggers")
        if not triggers:
            issues.append(
                LintIssue(
                    code="RULE_TRIGGER",
                    message=f"rule '{rule_name}' must declare triggers",
                    severity="error",
                    path=path,
                )
            )
        elif not isinstance(triggers, Sequence) or isinstance(triggers, (str, bytes, bytearray)):
            issues.append(
                LintIssue(
                    code="RULE_TRIGGER",
                    message=f"rule '{rule_name}' triggers must be a list",
                    severity="error",
                    path=f"{path}.triggers",
                )
            )
        else:
            for trigger in triggers:
                if not isinstance(trigger, str) or not trigger.strip():
                    issues.append(
                        LintIssue(
                            code="RULE_TRIGGER",
                            message=f"rule '{rule_name}' trigger must be a non-empty string",
                            severity="error",
                            path=f"{path}.triggers",
                        )
                    )
                if not _TRIGGER_PATTERN.match(trigger):
                    issues.append(
                        LintIssue(
                            code="RULE_TRIGGER",
                            message=f"rule '{rule_name}' trigger '{trigger}' contains invalid characters",
                            severity="error",
                            path=f"{path}.triggers",
                        )
                    )
    return issues
