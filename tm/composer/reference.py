from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, MutableMapping, Sequence

from tm.artifacts import validate_capability_spec, validate_workflow_policy
from tm.intent.validator import intent_precheck


class ComposerError(RuntimeError):
    """Raised when composition is impossible."""


REFERENCE_STEPS = [
    ("step_compute", "compute.process"),
    ("step_validate", "validate.result"),
    ("step_write", "external.write"),
]


def compose_reference_workflow(
    intent: Mapping[str, Any],
    *,
    policy: Mapping[str, Any],
    capabilities: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    for spec in capabilities:
        validate_capability_spec(spec)

    available = {str(spec["capability_id"]) for spec in capabilities}
    missing = [cap for _, cap in REFERENCE_STEPS if cap not in available]
    if missing:
        raise ComposerError(f"missing required capabilities: {', '.join(sorted(missing))}")

    precheck = intent_precheck(intent, policy=policy, capabilities=capabilities)
    if precheck.status != "valid":
        raise ComposerError(f"intent precheck failed: {precheck.reason}")

    steps = []
    for step_id, capability_id in REFERENCE_STEPS:
        step: MutableMapping[str, Any] = {
            "step_id": step_id,
            "capability_id": capability_id,
            "description": f"Invoke {capability_id}",
        }
        if capability_id == "external.write":
            step["guard"] = {
                "name": "external-write-approval",
                "type": "approval",
                "required_for": capability_id,
            }
        steps.append(step)

    transitions = [
        {"from": "step_compute", "to": "step_validate"},
        {"from": "step_validate", "to": "step_write"},
    ]

    explanation = {
        "intent_coverage": f"Fulfills goal {intent['goal']['target']}",
        "capability_reasoning": "compute -> validate -> guarded write",
        "constraint_coverage": "respects no_unvalidated_write invariant",
        "risks": ["external.write requires explicit guard"],
        "assumptions": "validation guarantees result.validated state",
        "unknowns": ["runtime tokens and approvals provided elsewhere"],
    }

    workflow = {
        "workflow_id": f"{policy['policy_id']}.reference",
        "intent_id": intent["intent_id"],
        "policy_id": policy["policy_id"],
        "name": "reference-workflow",
        "version": intent["version"],
        "steps": steps,
        "transitions": transitions,
        "guards": [
            {
                "name": "external-write-approval",
                "type": "approval",
                "scope": "workflow",
                "required_for": "external.write",
            }
        ],
        "explanation": explanation,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "metadata": {
            "precheck_reason": precheck.reason,
        },
    }

    validate_workflow_policy(workflow)
    return workflow


__all__ = ["ComposerError", "compose_reference_workflow"]
