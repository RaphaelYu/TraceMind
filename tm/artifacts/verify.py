from __future__ import annotations

import re
from typing import Any, Mapping, Sequence, Tuple

from .hash import body_hash
from .models import (
    AgentBundleBody,
    Artifact,
    ArtifactStatus,
    ArtifactType,
    PlanBody,
    PlanRule,
)
from .report import ArtifactVerificationReport
from tm.lint.io_contract_lint import lint_agent_bundle_io_contract, lint_plan_io_contract
from tm.lint.plan_lint import LintIssue

_SUPPORTED_VERSION_PREFIX = "v0"
_TRIGGER_PATTERN = re.compile(r"^[A-Za-z0-9_\.\[\]\*\$]+$")
_BUNDLE_PHASES = {"init", "run", "emit", "finalize"}


def _is_supported_version(version: str) -> bool:
    return version == _SUPPORTED_VERSION_PREFIX or version.startswith(f"{_SUPPORTED_VERSION_PREFIX}.")


def _validate_plan_steps(plan: PlanBody, raw_steps: Sequence[Any] | None, report: ArtifactVerificationReport) -> None:
    if raw_steps is None:
        report.add_error("plan body missing 'steps' definition")
        return
    if not isinstance(raw_steps, Sequence):
        report.add_error("plan.steps must be a sequence")
        return
    seen: set[str] = set()
    for idx, step in enumerate(plan.steps):
        path = f"steps[{idx}]"
        raw_step = raw_steps[idx] if idx < len(raw_steps) else {}
        if not isinstance(raw_step, Mapping):
            report.add_error(f"{path} must be a mapping")
            continue
        name = step.name
        if not name:
            report.add_error(f"{path}.name must be a non-empty string")
        else:
            if name in seen:
                report.add_error(f"{path}.name '{name}' is not unique")
            seen.add(name)
        if "reads" not in raw_step:
            report.add_error(f"{path} missing 'reads' field")
        elif not isinstance(step.reads, list):
            report.add_error(f"{path}.reads must be a list")
        if "writes" not in raw_step:
            report.add_error(f"{path} missing 'writes' field")
        elif not isinstance(step.writes, list):
            report.add_error(f"{path}.writes must be a list")


def _validate_rule(rule: PlanRule, step_names: Sequence[str], report: ArtifactVerificationReport) -> None:
    if not rule.triggers:
        report.add_error(f"rule '{rule.name}' must declare at least one trigger")
    for trigger in rule.triggers:
        if not isinstance(trigger, str) or not trigger.strip():
            report.add_error(f"rule '{rule.name}' trigger must be a non-empty string")
            continue
        if not _TRIGGER_PATTERN.match(trigger):
            report.add_error(f"rule '{rule.name}' trigger '{trigger}' contains invalid characters")
    if not rule.steps:
        report.add_error(f"rule '{rule.name}' must reference at least one step")
    for target in rule.steps:
        if target not in step_names:
            report.add_error(f"rule '{rule.name}' references undefined step '{target}'")


def _validate_plan_rules(plan: PlanBody, report: ArtifactVerificationReport) -> None:
    step_names = [step.name for step in plan.steps if step.name]
    for rule in plan.rules:
        _validate_rule(rule, step_names, report)


def _validate_plan_body(body: PlanBody, raw_body: Mapping[str, Any], report: ArtifactVerificationReport) -> None:
    raw_steps = raw_body.get("steps")
    _validate_plan_steps(body, raw_steps, report)
    raw_rules = raw_body.get("rules", [])
    if raw_rules is not None and not isinstance(raw_rules, Sequence):
        report.add_error("plan.rules must be a sequence if provided")
    _validate_plan_rules(body, report)
    lint_issues = lint_plan_io_contract(raw_body)
    _report_lint_issues(report, lint_issues)


def _report_lint_issues(report: ArtifactVerificationReport, issues: Sequence[LintIssue]) -> None:
    for issue in issues:
        suffix = f" (path: {issue.path})" if issue.path else ""
        report.add_error(f"{issue.code}: {issue.message}{suffix}")


def _validate_agent_bundle(
    body: AgentBundleBody, raw_body: Mapping[str, Any], report: ArtifactVerificationReport
) -> None:
    if not body.agents:
        report.add_error("agent bundle must declare at least one agent")
    agent_ids = {agent.spec.agent_id for agent in body.agents}
    raw_plan = raw_body.get("plan")
    if raw_plan is None:
        report.add_error("agent bundle missing 'plan'")
        return
    if not isinstance(raw_plan, Sequence) or isinstance(raw_plan, str):
        report.add_error("agent bundle plan must be a sequence")
        return
    for idx, step in enumerate(body.plan):
        path = f"plan[{idx}]"
        if not step.step:
            report.add_error(f"{path}.step must be a non-empty string")
        if not step.agent_id:
            report.add_error(f"{path}.agent_id must be a non-empty string")
        elif step.agent_id not in agent_ids:
            report.add_error(f"{path}.agent_id '{step.agent_id}' is not registered")
        if step.phase and step.phase not in _BUNDLE_PHASES:
            report.add_error(f"{path}.phase '{step.phase}' is not allowed")
        if not isinstance(step.inputs, list):
            report.add_error(f"{path}.inputs must be a list")
        if not isinstance(step.outputs, list):
            report.add_error(f"{path}.outputs must be a list")


def _apply_success_metadata(artifact: Artifact, computed_hash: str) -> None:
    artifact.envelope.body_hash = computed_hash
    hashes = artifact.envelope.meta.get("hashes")
    if not isinstance(hashes, dict):
        hashes = {}
    hashes["body_hash"] = computed_hash
    artifact.envelope.meta["hashes"] = hashes
    artifact.envelope.meta["determinism"] = True
    artifact.envelope.meta["produced_by"] = f"tracemind.verifier.{_SUPPORTED_VERSION_PREFIX}"
    artifact.envelope.status = ArtifactStatus.ACCEPTED


def verify(candidate: Artifact) -> Tuple[Artifact | None, ArtifactVerificationReport]:
    report = ArtifactVerificationReport(artifact_id=candidate.envelope.artifact_id)
    if candidate.envelope.status != ArtifactStatus.CANDIDATE:
        report.add_error("artifact status must be 'candidate' for verification")
    if not _is_supported_version(candidate.envelope.version):
        report.add_error(f"unsupported artifact version '{candidate.envelope.version}'")
    if candidate.envelope.artifact_type == ArtifactType.PLAN and isinstance(candidate.body, PlanBody):
        _validate_plan_body(candidate.body, candidate.body_raw, report)
    if candidate.envelope.artifact_type == ArtifactType.AGENT_BUNDLE and isinstance(candidate.body, AgentBundleBody):
        _validate_agent_bundle(candidate.body, candidate.body_raw, report)
        lint_issues = lint_agent_bundle_io_contract(candidate.body, candidate.body_raw)
        _report_lint_issues(report, lint_issues)
    if report.errors:
        return None, report
    computed = body_hash(candidate.body_raw)
    _apply_success_metadata(candidate, computed)
    report.details["body_hash"] = computed
    report.mark_success()
    return candidate, report
