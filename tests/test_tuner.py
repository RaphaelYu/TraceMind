import random

import pytest

from tm.ai.tuner import BanditTuner, EpsilonGreedy, UCB1


def _simulate(strategy, *, rounds: int = 400) -> dict[str, int]:
    means = {"arm_a": 0.2, "arm_b": 0.8}
    counts = {"arm_a": 0, "arm_b": 0}
    arms = {"arm_a": {}, "arm_b": {}}
    random.seed(42)
    for _ in range(rounds):
        choice = strategy.select("flow", "policy", arms)
        counts[choice] += 1
        reward = random.gauss(means[choice], 0.1)
        strategy.update("flow", "policy", choice, reward)
    return counts


def test_epsilon_greedy_prefers_better_arm():
    strategy = EpsilonGreedy(epsilon=0.1, seed=7)
    counts = _simulate(strategy)
    assert counts["arm_b"] > counts["arm_a"]


def test_ucb1_prefers_better_arm():
    strategy = UCB1(c=0.8)
    counts = _simulate(strategy)
    assert counts["arm_b"] > counts["arm_a"]


@pytest.mark.asyncio
async def test_bandit_tuner_async_wrapper_tracks_stats():
    tuner = BanditTuner(strategy_factory=lambda: EpsilonGreedy(epsilon=0.2, seed=11))
    binding = "demo:read"
    candidates = ["arm_a", "arm_b"]

    for _ in range(50):
        choice = await tuner.choose(binding, candidates)
        reward = 1.0 if choice == "arm_b" else 0.0
        await tuner.update(binding, choice, reward)

    stats = await tuner.stats(binding)
    assert stats["arm_b"]["pulls"] > 0
    assert stats["arm_b"]["avg_reward"] >= stats["arm_a"]["avg_reward"]
