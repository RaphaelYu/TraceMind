from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Sequence, Set, Tuple

from tm.agents.models import AgentContract
from tm.artifacts.models import AgentBundleBody
from tm.lint.plan_lint import LintIssue


@dataclass
class IORefMeta:
    kind: str
    schema_repr: str
    owners: Set[str]
    modes: Set[str]


def _normalize_schema_value(schema: Mapping[str, Any] | str) -> str:
    if isinstance(schema, str):
        return schema
    try:
        return json.dumps(schema, sort_keys=True)
    except TypeError:
        return str(schema)


def _requires_effect(mode: str) -> bool:
    return "write" in mode or "mutate" in mode


def _collect_ref_registry(
    contract_entries: Sequence[Tuple[str, AgentContract]],
) -> Tuple[Dict[str, IORefMeta], List[LintIssue]]:
    registry: Dict[str, IORefMeta] = {}
    issues: List[LintIssue] = []
    for label, contract in contract_entries:
        for io_ref in contract.inputs + contract.outputs:
            schema_repr = _normalize_schema_value(io_ref.schema)
            entry = registry.get(io_ref.ref)
            if entry is None:
                entry = IORefMeta(kind=io_ref.kind, schema_repr=schema_repr, owners=set(), modes=set())
                registry[io_ref.ref] = entry
            else:
                if entry.kind != io_ref.kind:
                    issues.append(
                        LintIssue(
                            code="IO_REF_KIND",
                            message=f"IORef '{io_ref.ref}' kind '{io_ref.kind}' conflicts with previously declared '{entry.kind}'",
                            severity="error",
                            path=f"{label}.contract",
                        )
                    )
                if entry.schema_repr != schema_repr:
                    issues.append(
                        LintIssue(
                            code="IO_REF_SCHEMA",
                            message=f"IORef '{io_ref.ref}' schema differs from other declarations",
                            severity="error",
                            path=f"{label}.contract",
                        )
                    )
            entry.owners.add(label)
            entry.modes.add(io_ref.mode)
    return registry, issues


def _validate_contract_effects(
    label: str,
    contract: AgentContract,
    registry: Dict[str, IORefMeta],
    issues: List[LintIssue],
) -> None:
    effect_targets = {effect.target for effect in contract.effects}
    _input_refs = {io_ref.ref for io_ref in contract.inputs}
    _output_refs = {io_ref.ref for io_ref in contract.outputs}
    for effect in contract.effects:
        path = f"{label}.contract.effects"
        if effect.target not in registry:
            issues.append(
                LintIssue(
                    code="EFFECT_TARGET",
                    message=f"Effect '{effect.name}' targets undeclared IORef '{effect.target}'",
                    severity="error",
                    path=path,
                )
            )
        if effect.kind == "resource" and not effect.idempotency.key_fields:
            issues.append(
                LintIssue(
                    code="RESOURCE_IDEMPOTENCY",
                    message=f"Effect '{effect.name}' must declare idempotency key fields",
                    severity="error",
                    path=path,
                )
            )
    for io_ref in contract.outputs:
        if _requires_effect(io_ref.mode) and io_ref.ref not in effect_targets:
            issues.append(
                LintIssue(
                    code="EFFECT_REQUIRED",
                    message=f"IORef '{io_ref.ref}' with mode '{io_ref.mode}' needs an effect declaration",
                    severity="error",
                    path=f"{label}.contract.outputs",
                )
            )


def _build_contract_io_sets(
    contract_entries: Sequence[Tuple[str, AgentContract]],
) -> Dict[str, Tuple[Set[str], Set[str]]]:
    result: Dict[str, Tuple[Set[str], Set[str]]] = {}
    for label, contract in contract_entries:
        inputs = {io_ref.ref for io_ref in contract.inputs}
        outputs = {io_ref.ref for io_ref in contract.outputs}
        result[label] = (inputs, outputs)
    return result


def _extract_preconditions(raw_body: Mapping[str, Any]) -> List[str]:
    meta = raw_body.get("meta")
    if not isinstance(meta, Mapping):
        return []
    preconditions = meta.get("preconditions")
    if not preconditions:
        return []
    if not isinstance(preconditions, Sequence) or isinstance(preconditions, (str, bytes, bytearray)):
        return []
    return [str(item) for item in preconditions]


def _lint_agent_bundle_plan(
    bundle: AgentBundleBody,
    raw_body: Mapping[str, Any],
    contract_io_sets: Dict[str, Tuple[Set[str], Set[str]]],
    issues: List[LintIssue],
) -> None:
    available_refs = set(_extract_preconditions(raw_body))
    for idx, step in enumerate(bundle.plan):
        path = f"plan[{idx}]"
        contract_sets = contract_io_sets.get(step.agent_id)
        if contract_sets is None:
            continue
        expected_inputs, expected_outputs = contract_sets
        for input_ref in step.inputs:
            if input_ref not in available_refs:
                issues.append(
                    LintIssue(
                        code="IO_CLOSURE",
                        message=f"Step '{step.step}' reads '{input_ref}' before it is produced",
                        severity="error",
                        path=f"{path}.inputs",
                    )
                )
            if input_ref not in expected_inputs:
                issues.append(
                    LintIssue(
                        code="IO_BINDING",
                        message=f"Agent '{step.agent_id}' does not declare input '{input_ref}'",
                        severity="error",
                        path=f"{path}.inputs",
                    )
                )
        for output_ref in step.outputs:
            if output_ref not in expected_outputs:
                issues.append(
                    LintIssue(
                        code="IO_BINDING",
                        message=f"Agent '{step.agent_id}' does not declare output '{output_ref}'",
                        severity="error",
                        path=f"{path}.outputs",
                    )
                )
            available_refs.add(output_ref)


def lint_agent_bundle_io_contract(bundle: AgentBundleBody, raw_body: Mapping[str, Any]) -> List[LintIssue]:
    issues: List[LintIssue] = []
    contract_entries = [(agent.spec.agent_id, agent.spec.contract) for agent in bundle.agents]
    if not contract_entries:
        return issues
    registry, registry_issues = _collect_ref_registry(contract_entries)
    issues.extend(registry_issues)
    for label, contract in contract_entries:
        _validate_contract_effects(label, contract, registry, issues)
    contract_io_sets = _build_contract_io_sets(contract_entries)
    _lint_agent_bundle_plan(bundle, raw_body, contract_io_sets, issues)
    return issues


def lint_plan_io_contract(plan_body: Mapping[str, Any]) -> List[LintIssue]:
    contract_raw = plan_body.get("io_contract")
    if not isinstance(contract_raw, Mapping):
        return []
    try:
        contract = AgentContract.from_mapping(contract_raw)
    except (TypeError, ValueError) as exc:
        return [
            LintIssue(
                code="IO_CONTRACT_PARSE",
                message=str(exc),
                severity="error",
                path="io_contract",
            )
        ]
    issues: List[LintIssue] = []
    registry, registry_issues = _collect_ref_registry([("plan", contract)])
    issues.extend(registry_issues)
    _validate_contract_effects("plan", contract, registry, issues)
    return issues
