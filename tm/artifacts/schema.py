from __future__ import annotations

from typing import Any, Mapping

Schema = Mapping[str, Any]

_IDENTIFIER_PATTERN = r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$"
_DATE_TIME_SCHEMA: Schema = {"type": "string", "format": "date-time"}

_PROPERTY_DESCRIPTOR: Schema = {
    "type": "object",
    "properties": {
        "type": {"type": "string"},
        "required": {"type": "boolean"},
        "description": {"type": "string"},
        "default": {},
        "schema": {"type": "object"},
    },
    "required": ["type"],
    "additionalProperties": False,
}

_GOAL_SCHEMA: Schema = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": ["achieve", "avoid", "maintain"]},
        "target": {"type": "string"},
        "description": {"type": "string"},
        "parameters": {"type": "object"},
    },
    "required": ["type", "target"],
    "additionalProperties": False,
}

_CONSTRAINT_SCHEMA: Schema = {
    "type": "object",
    "properties": {
        "type": {"type": "string"},
        "rule": {"type": "string"},
        "value": {},
        "description": {"type": "string"},
        "context": {"type": "object"},
    },
    "required": ["type", "rule"],
    "additionalProperties": False,
}

_PREFERENCE_SCHEMA: Schema = {
    "type": "object",
    "properties": {
        "type": {"type": "string"},
        "weight": {"anyOf": [{"type": "string"}, {"type": "number"}]},
        "description": {"type": "string"},
    },
    "required": ["type"],
    "additionalProperties": False,
}

_INTENT_SPEC_SCHEMA: Schema = {
    "type": "object",
    "properties": {
        "intent_id": {"type": "string", "pattern": _IDENTIFIER_PATTERN},
        "version": {"type": "string"},
        "goal": _GOAL_SCHEMA,
        "constraints": {"type": "array", "items": _CONSTRAINT_SCHEMA},
        "preferences": {"type": "array", "items": _PREFERENCE_SCHEMA},
        "context_refs": {"type": "array", "items": {"type": "string"}},
        "metadata": {"type": "object"},
    },
    "required": ["intent_id", "version", "goal"],
    "additionalProperties": False,
}

_EVENT_TYPE_SCHEMA: Schema = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "pattern": _IDENTIFIER_PATTERN},
        "payload_schema": {"type": "object"},
        "description": {"type": "string"},
    },
    "required": ["name"],
    "additionalProperties": False,
}

_STATE_EXTRACTOR_SCHEMA: Schema = {
    "type": "object",
    "properties": {
        "from_event": {"type": "string"},
        "produces": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "type": {"type": "string"},
                    "value": {},
                    "stability": {"type": "string", "enum": ["stable", "unstable", "derived"]},
                },
                "required": ["type"],
                "additionalProperties": False,
            },
        },
        "description": {"type": "string"},
    },
    "required": ["from_event", "produces"],
    "additionalProperties": False,
}

_SAFETY_CONTRACT_SCHEMA: Schema = {
    "type": "object",
    "properties": {
        "determinism": {"type": "boolean"},
        "side_effects": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "rollback": {
            "type": "object",
            "properties": {
                "supported": {"type": "boolean"},
                "strategy": {"type": "string"},
            },
            "required": ["supported"],
            "additionalProperties": False,
        },
        "isolation_level": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["determinism", "side_effects"],
    "additionalProperties": False,
}

_CAPABILITY_SPEC_SCHEMA: Schema = {
    "type": "object",
    "properties": {
        "capability_id": {"type": "string", "pattern": _IDENTIFIER_PATTERN},
        "version": {"type": "string"},
        "description": {"type": "string"},
        "inputs": {"type": "object", "additionalProperties": _PROPERTY_DESCRIPTOR},
        "outputs": {"type": "object", "additionalProperties": _PROPERTY_DESCRIPTOR},
        "config_schema": {"type": "object", "additionalProperties": _PROPERTY_DESCRIPTOR},
        "event_types": {"type": "array", "items": _EVENT_TYPE_SCHEMA},
        "state_extractors": {"type": "array", "items": _STATE_EXTRACTOR_SCHEMA},
        "safety_contract": _SAFETY_CONTRACT_SCHEMA,
        "execution_binding": {
            "type": "object",
            "properties": {
                "type": {"type": "string"},
                "ref": {"type": "string"},
                "metadata": {"type": "object"},
            },
            "required": ["type"],
            "additionalProperties": False,
        },
    },
    "required": ["capability_id", "version", "inputs", "event_types", "safety_contract"],
    "additionalProperties": False,
}

_STATE_SCHEMA_ENTRY: Schema = {
    "type": "object",
    "properties": {
        "type": {"type": "string"},
        "source": {"type": "string"},
        "stability": {"type": "string", "enum": ["stable", "unstable", "derived"]},
    },
    "required": ["type"],
    "additionalProperties": False,
}

_INVARIANT_SCHEMA: Schema = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "type": {"type": "string"},
        "condition": {"type": "string"},
        "description": {"type": "string"},
    },
    "required": ["id", "type", "condition"],
    "additionalProperties": False,
}

_LIVENESS_SCHEMA: Schema = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "type": {"type": "string"},
        "condition": {"type": "string"},
        "within": {"type": "string"},
    },
    "required": ["id", "type", "condition"],
    "additionalProperties": False,
}

_GUARD_SCHEMA: Schema = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "type": {"type": "string"},
        "scope": {"type": "string"},
        "required_for": {
            "anyOf": [
                {"type": "string"},
                {"type": "array", "items": {"type": "string"}, "minItems": 1},
            ]
        },
        "config": {"type": "object"},
    },
    "required": ["type"],
    "additionalProperties": False,
}

_POLICY_SPEC_SCHEMA: Schema = {
    "type": "object",
    "properties": {
        "policy_id": {"type": "string", "pattern": _IDENTIFIER_PATTERN},
        "version": {"type": "string"},
        "description": {"type": "string"},
        "state_schema": {
            "type": "object",
            "patternProperties": {"[a-zA-Z0-9_.-]+": _STATE_SCHEMA_ENTRY},
            "additionalProperties": False,
        },
        "invariants": {"type": "array", "items": _INVARIANT_SCHEMA},
        "liveness": {"type": "array", "items": _LIVENESS_SCHEMA},
        "guards": {"type": "array", "items": _GUARD_SCHEMA},
        "metadata": {"type": "object"},
    },
    "required": ["policy_id", "version", "state_schema"],
    "additionalProperties": False,
}

_STEP_SCHEMA: Schema = {
    "type": "object",
    "properties": {
        "step_id": {"type": "string"},
        "capability_id": {"type": "string", "pattern": _IDENTIFIER_PATTERN},
        "description": {"type": "string"},
        "inputs": {"type": "object"},
        "outputs": {"type": "object"},
        "guard": _GUARD_SCHEMA,
        "metadata": {"type": "object"},
    },
    "required": ["step_id", "capability_id"],
    "additionalProperties": False,
}

_TRANSITION_SCHEMA: Schema = {
    "type": "object",
    "properties": {
        "from": {"type": "string"},
        "to": {"type": "string"},
        "condition": {"type": "string"},
        "type": {"type": "string"},
    },
    "required": ["from", "to"],
    "additionalProperties": False,
}

_EXPLANATION_SCHEMA: Schema = {
    "type": "object",
    "properties": {
        "intent_coverage": {"type": "string"},
        "capability_reasoning": {"type": "string"},
        "constraint_coverage": {"type": "string"},
        "risks": {"type": "array", "items": {"type": "string"}},
        "assumptions": {"type": "string"},
        "unknowns": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["intent_coverage", "capability_reasoning", "constraint_coverage", "risks"],
    "additionalProperties": False,
}

_WORKFLOW_POLICY_SCHEMA: Schema = {
    "type": "object",
    "properties": {
        "workflow_id": {"type": "string", "pattern": _IDENTIFIER_PATTERN},
        "intent_id": {"type": "string", "pattern": _IDENTIFIER_PATTERN},
        "policy_id": {"type": "string", "pattern": _IDENTIFIER_PATTERN},
        "name": {"type": "string"},
        "description": {"type": "string"},
        "version": {"type": "string"},
        "steps": {"type": "array", "items": _STEP_SCHEMA, "minItems": 1},
        "transitions": {"type": "array", "items": _TRANSITION_SCHEMA},
        "guards": {"type": "array", "items": _GUARD_SCHEMA},
        "explanation": _EXPLANATION_SCHEMA,
        "created_at": _DATE_TIME_SCHEMA,
        "metadata": {"type": "object"},
    },
    "required": ["workflow_id", "intent_id", "policy_id", "steps", "explanation"],
    "additionalProperties": False,
}

_TRACE_ENTRY_SCHEMA: Schema = {
    "type": "object",
    "properties": {
        "time": _DATE_TIME_SCHEMA,
        "unit": {"type": "string"},
        "status": {"type": "string"},
        "event": {"type": "string"},
        "details": {"type": "object"},
    },
    "required": ["time", "unit"],
    "additionalProperties": False,
}

_EXECUTION_TRACE_SCHEMA: Schema = {
    "type": "object",
    "properties": {
        "trace_id": {"type": "string"},
        "workflow_id": {"type": "string"},
        "workflow_revision": {"type": "string"},
        "run_id": {"type": "string"},
        "intent_id": {"type": "string"},
        "timestamp": _DATE_TIME_SCHEMA,
        "entries": {"type": "array", "items": _TRACE_ENTRY_SCHEMA},
        "state_snapshot": {"type": "object"},
        "violations": {"type": "array", "items": {"type": "string"}},
        "metadata": {"type": "object"},
    },
    "required": ["trace_id", "workflow_id", "run_id", "entries", "timestamp"],
    "additionalProperties": False,
}

_BLAME_SCHEMA: Schema = {
    "type": "object",
    "properties": {
        "capability": {"type": "string"},
        "policy": {"type": "string"},
        "guard": {"type": "string"},
        "step": {"type": "string"},
    },
    "additionalProperties": False,
}

_INTEGRATED_STATE_REPORT_SCHEMA: Schema = {
    "type": "object",
    "properties": {
        "report_id": {"type": "string"},
        "workflow_id": {"type": "string"},
        "intent_id": {"type": "string"},
        "status": {"type": "string", "enum": ["satisfied", "violated", "unknown"]},
        "violated_rules": {"type": "array", "items": {"type": "string"}},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "blame": _BLAME_SCHEMA,
        "timestamp": _DATE_TIME_SCHEMA,
        "metadata": {"type": "object"},
    },
    "required": ["report_id", "workflow_id", "status", "timestamp"],
    "additionalProperties": False,
}

_PATCH_CHANGE_SCHEMA: Schema = {
    "type": "object",
    "properties": {
        "path": {"type": "string"},
        "value": {},
        "op": {"type": "string", "enum": ["set", "remove"]},
        "note": {"type": "string"},
    },
    "required": ["path"],
    "additionalProperties": False,
}

_PATCH_PROPOSAL_SCHEMA: Schema = {
    "type": "object",
    "properties": {
        "proposal_id": {"type": "string"},
        "source": {"type": "string", "enum": ["violation", "analysis", "human", "ai"]},
        "target": {"type": "string", "enum": ["policy", "intent", "workflow", "config"]},
        "description": {"type": "string"},
        "rationale": {"type": "string"},
        "expected_effect": {"type": "string"},
        "changes": {"type": "array", "items": _PATCH_CHANGE_SCHEMA},
        "created_at": _DATE_TIME_SCHEMA,
        "metadata": {"type": "object"},
    },
    "required": ["proposal_id", "source", "target", "description", "rationale", "expected_effect"],
    "additionalProperties": False,
}

SCHEMAS: Mapping[str, Schema] = {
    "IntentSpec": _INTENT_SPEC_SCHEMA,
    "CapabilitySpec": _CAPABILITY_SPEC_SCHEMA,
    "PolicySpec": _POLICY_SPEC_SCHEMA,
    "WorkflowPolicy": _WORKFLOW_POLICY_SCHEMA,
    "ExecutionTrace": _EXECUTION_TRACE_SCHEMA,
    "IntegratedStateReport": _INTEGRATED_STATE_REPORT_SCHEMA,
    "PatchProposal": _PATCH_PROPOSAL_SCHEMA,
}
