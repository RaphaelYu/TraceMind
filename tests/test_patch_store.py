import json
from pathlib import Path

from tm.patch.store import PatchStore, PatchStoreError


def _write_policy(path: Path) -> None:
    policy = {
        "policy_id": "policy.reference",
        "version": "1.0.0",
        "state_schema": {"result.validated": {"type": "boolean"}},
        "invariants": [],
        "guards": [],
    }
    path.write_text(json.dumps(policy), encoding="utf-8")


def test_patch_store_lifecycle(tmp_path: Path) -> None:
    policy_path = tmp_path / "policy.json"
    _write_policy(policy_path)
    store_root = tmp_path / ".tm_patches"
    store = PatchStore(root=store_root)
    changes = [
        {
            "op": "add",
            "path": "/guards",
            "value": [{"name": "external-write-approval", "type": "approval"}],
        }
    ]
    entry = store.create_draft(
        changes=changes,
        target_artifact_type="policy",
        target_ref=str(policy_path),
        patch_kind="tighten_guard",
        rationale="add guard",
        expected_effect="prevent unvalidated writes",
        risk_level="medium",
        created_by="tester",
    )
    assert entry.status == "DRAFT"
    assert (store.proposals_dir / f"{entry.proposal_id}.json").exists()

    store.submit_proposal(entry.proposal_id)
    index = store.describe()
    assert index["proposals"][entry.proposal_id]["status"] == "SUBMITTED"

    store.approve_proposal(entry.proposal_id, actor="owner", reason="approved")
    assert store.describe()["proposals"][entry.proposal_id]["status"] == "APPROVED"

    dest = store.apply_proposal(entry.proposal_id)
    assert dest.exists()
    stored = store.describe()
    assert stored["proposals"][entry.proposal_id]["status"] == "APPLIED"
    assert stored["applied"][-1]["proposal_id"] == entry.proposal_id
    assert "applied_at" in stored["proposals"][entry.proposal_id]


def test_patch_store_invalid_submit(tmp_path: Path) -> None:
    store = PatchStore(root=tmp_path / ".tm_patches")
    with open(tmp_path / "patch.json", "w", encoding="utf-8") as fh:
        fh.write("{}")
    try:
        store.submit_proposal("missing")
    except PatchStoreError:
        pass
    else:
        raise AssertionError("expected PatchStoreError for unknown proposal")
