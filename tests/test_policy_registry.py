from __future__ import annotations

import json

import pytest

from tm.ai.policy_registry import (
    PolicyLoader,
    PolicyError,
    policy_registry,
    apply_policy,
)
from tm.ai.tuner import BanditTuner


@pytest.mark.asyncio
async def test_policy_loader_registers_and_biases_tuner():
    policy_registry._policies.clear()  # type: ignore[attr-defined]
    loader = PolicyLoader()
    recipe = {
        "policy": {
            "id": "demo:read",
            "strategy": "epsilon",
            "params": {"alpha": 0.6, "exploration_bonus": 0.0},
            "arms": ["flow_a", "flow_b"],
        }
    }
    definition = loader.load(json.dumps(recipe))
    assert definition.policy_id == "demo:read"
    assert list(definition.arms or []) == ["flow_a", "flow_b"]

    tuner = BanditTuner(strategy="epsilon", epsilon=0.3)
    await apply_policy(tuner, definition.policy_id)

    counts = {"flow_a": 0, "flow_b": 0}
    for _ in range(100):
        choice = await tuner.choose(definition.policy_id, definition.arms or [])
        counts[choice] += 1
        reward = 1.0 if choice == "flow_b" else 0.0
        await tuner.update(definition.policy_id, choice, reward)

    assert counts["flow_b"] > counts["flow_a"]


def test_invalid_policy_recipe():
    policy_registry._policies.clear()  # type: ignore[attr-defined]
    loader = PolicyLoader()
    bad = {"policy": {"id": "", "strategy": "epsilon"}}
    with pytest.raises(PolicyError):
        loader.load(json.dumps(bad))
