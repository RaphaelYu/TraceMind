import pytest

from tm.artifacts import ArtifactValidationError, validate_intent_spec, validate_patch_proposal


def test_validate_intent_spec_accepts_minimal_payload() -> None:
    payload = {
        "intent_id": "intent.create.result",
        "version": "1.0.0",
        "goal": {"type": "achieve", "target": "result.validated"},
    }
    validate_intent_spec(payload)


def test_validate_intent_spec_rejects_missing_version() -> None:
    payload = {
        "intent_id": "intent.create.result",
        "goal": {"type": "achieve", "target": "result.validated"},
    }
    with pytest.raises(ArtifactValidationError) as excinfo:
        validate_intent_spec(payload)
    assert "version" in str(excinfo.value)


def test_validate_patch_proposal_requires_rationale() -> None:
    payload = {
        "proposal_id": "patch-123",
        "source": "analysis",
        "target": "policy",
        "description": "Add a guard",
        "expected_effect": "Prevent unvalidated writes",
    }
    with pytest.raises(ArtifactValidationError) as excinfo:
        validate_patch_proposal(payload)
    assert "rationale" in str(excinfo.value)


def test_validate_patch_proposal_accepts_complete_payload() -> None:
    payload = {
        "proposal_id": "patch-123",
        "source": "analysis",
        "target": "policy",
        "description": "Add a guard",
        "rationale": "Policy review flagged a hole",
        "expected_effect": "Prevent unvalidated writes",
        "changes": [{"path": "guards[0].type", "value": "approval"}],
    }
    validate_patch_proposal(payload)
