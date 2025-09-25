import json
from pathlib import Path

from tm.ai.policy_store import PolicyStore
from tm.ai.proposals import Change, Proposal


def test_policy_store_apply_updates_state(tmp_path):
    path = tmp_path / "policies.json"
    store = PolicyStore(path)

    proposal = Proposal(
        proposal_id="p-1",
        title="Set limit",
        summary="Adjust flow limit",
        changes=[Change(path="limits.flow", value=3)],
    )

    version = store.apply(proposal, actor="tester", reason="unit test")

    assert version == 1
    assert store.version() == 1
    assert store.get("limits.flow") == 3

    history = store.history()
    assert history[-1]["proposal"]["id"] == "p-1"
