import pytest

from tm.ai.tuner import BanditTuner


@pytest.mark.asyncio
async def test_bandit_tuner_prefers_high_reward_arm():
    tuner = BanditTuner(alpha=0.5, exploration_bonus=0.0)
    binding = "demo:read"
    candidates = ["flow_a", "flow_b"]

    first = await tuner.choose(binding, candidates)
    second = await tuner.choose(binding, candidates)
    assert {first, second} == set(candidates)

    await tuner.update(binding, "flow_a", -1.0)
    await tuner.update(binding, "flow_b", 1.0)
    await tuner.update(binding, "flow_b", 1.0)

    choices = [await tuner.choose(binding, candidates) for _ in range(6)]
    assert choices.count("flow_b") > choices.count("flow_a")

    stats = await tuner.stats(binding)
    assert stats["flow_b"]["score"] > stats["flow_a"]["score"]
