import pytest

from tm.composer import WorkflowComposer


def _intent_spec() -> dict:
    return {
        "intent_id": "intent.compute.reference",
        "version": "1.0.0",
        "goal": {"type": "achieve", "target": "result.validated"},
    }


def _policy_spec(with_guard: bool = True) -> dict:
    policy = {
        "policy_id": "policy.reference",
        "version": "1.0.0",
        "state_schema": {"result.validated": {"type": "boolean"}},
        "invariants": [{"id": "inv.no_unvalidated_external_write", "type": "never", "condition": "result.unvalidated"}],
    }
    if with_guard:
        policy["guards"] = [
            {
                "name": "external-write-approval",
                "type": "approval",
                "scope": "workflow",
                "required_for": ["external.write", "external.notify"],
            }
        ]
    else:
        policy["guards"] = []
    return policy


def _capability_spec(
    capability_id: str,
    *,
    side_effects: list[str],
    rollback_supported: bool,
    determinism: bool,
    produces: dict[str, dict[str, bool]],
) -> dict:
    return {
        "capability_id": capability_id,
        "version": "0.1.0",
        "description": f"Capability {capability_id}",
        "inputs": {},
        "outputs": {},
        "event_types": [{"name": f"{capability_id}.done"}],
        "state_extractors": [
            {
                "from_event": f"{capability_id}.done",
                "produces": produces,
            }
        ],
        "safety_contract": {
            "determinism": determinism,
            "side_effects": side_effects,
            "rollback": {"supported": rollback_supported},
        },
    }


def _catalog() -> list[dict]:
    return [
        _capability_spec(
            "compute.process",
            side_effects=[],
            rollback_supported=True,
            determinism=True,
            produces={"prediction.ready": {"type": "boolean", "value": True}},
        ),
        _capability_spec(
            "validate.result",
            side_effects=[],
            rollback_supported=True,
            determinism=True,
            produces={
                "result.validated": {"type": "boolean", "value": True},
                "result.unvalidated": {"type": "boolean", "value": False},
            },
        ),
        _capability_spec(
            "external.write",
            side_effects=["external_io"],
            rollback_supported=False,
            determinism=True,
            produces={"external.write.performed": {"type": "boolean", "value": True}},
        ),
        _capability_spec(
            "case.create",
            side_effects=[],
            rollback_supported=True,
            determinism=True,
            produces={"case.created": {"type": "boolean", "value": True}},
        ),
        _capability_spec(
            "audit.record",
            side_effects=[],
            rollback_supported=True,
            determinism=True,
            produces={"audit.logged": {"type": "boolean", "value": True}},
        ),
        _capability_spec(
            "external.notify",
            side_effects=["notification"],
            rollback_supported=False,
            determinism=True,
            produces={"external.notify.sent": {"type": "boolean", "value": True}},
        ),
    ]


def test_workflow_composer_scores_reference_templates() -> None:
    composer = WorkflowComposer(
        intent=_intent_spec(),
        policy=_policy_spec(),
        capabilities=_catalog(),
        intent_ref="intent.yaml",
        policy_ref="policy.yaml",
        catalog_ref="catalog.json",
    )
    result = composer.compose(["conservative", "aggressive"], top_k=1)
    accepted = result["explanation"]["compose_result"]["accepted"]
    assert len(accepted) == 2

    conservative = accepted[0]
    aggressive = accepted[1]

    assert conservative["mode"] == "conservative"
    assert pytest.approx(3.8333333, rel=1e-6) == conservative["score"]["total_cost"]
    assert aggressive["mode"] == "aggressive"
    assert pytest.approx(3.1666666, rel=1e-6) == aggressive["score"]["total_cost"]
    assert conservative["template"] == "T1"
    assert "side-effect" in conservative["rationale"][0].lower() or "no side effects" in conservative["rationale"][0]

    workflow_policy = result["workflow_policy"]
    assert workflow_policy["workflow_id"].startswith("policy.reference.t1")
    assert any(step["capability_id"] == "external.write" for step in workflow_policy["steps"])
    explanation = result["explanation"]["compose_result"]
    assert explanation["modes"] == ["conservative", "aggressive"]


def test_workflow_composer_reports_guard_missing() -> None:
    composer = WorkflowComposer(
        intent=_intent_spec(),
        policy=_policy_spec(with_guard=False),
        capabilities=_catalog(),
        intent_ref="intent.yaml",
        policy_ref="policy.yaml",
        catalog_ref="catalog.json",
    )
    result = composer.compose(["conservative"], top_k=1)
    assert result["workflow_policy"] == {}
    rejected = result["explanation"]["compose_result"]["rejected"]
    assert any(entry["rejection"]["code"] == "GUARD_REQUIRED_BUT_MISSING" for entry in rejected)
