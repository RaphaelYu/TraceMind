import pytest

from tm.ai.feedback import FeedbackEvent, reward
from tm.ai.reward_config import RewardWeights, load_reward_weights


def test_reward_ok_beats_error():
    weights = RewardWeights()
    ok = reward(FeedbackEvent(outcome="ok", duration_ms=100.0, cost_usd=0.1), weights)
    error = reward(FeedbackEvent(outcome="error", duration_ms=100.0, cost_usd=0.1), weights)
    assert ok > error


def test_reward_ok_beats_rejected():
    weights = RewardWeights()
    ok = reward(FeedbackEvent(outcome="ok"), weights)
    rejected = reward(FeedbackEvent(outcome="rejected"), weights)
    assert ok > rejected


def test_reward_low_latency_scores_higher():
    weights = RewardWeights()
    fast = reward(FeedbackEvent(outcome="ok", duration_ms=50.0), weights)
    slow = reward(FeedbackEvent(outcome="ok", duration_ms=400.0), weights)
    assert fast > slow


def test_reward_low_cost_scores_higher():
    weights = RewardWeights()
    cheap = reward(FeedbackEvent(outcome="ok", cost_usd=0.01), weights)
    pricey = reward(FeedbackEvent(outcome="ok", cost_usd=2.0), weights)
    assert cheap > pricey


def test_reward_user_rating_bonus():
    weights = RewardWeights()
    rated = reward(FeedbackEvent(outcome="ok", user_rating=0.9), weights)
    neutral = reward(FeedbackEvent(outcome="ok"), weights)
    assert rated > neutral


def test_reward_task_success_bonus():
    weights = RewardWeights()
    success = reward(FeedbackEvent(outcome="error", task_success=1.0), weights)
    failure = reward(FeedbackEvent(outcome="error", task_success=0.0), weights)
    assert success > failure


def test_reward_clamped():
    weights = RewardWeights(outcome_ok=1.0, user_rating=1.0, task_success=1.0)
    value = reward(FeedbackEvent(outcome="ok", user_rating=1.0, task_success=1.0), weights)
    assert -1.0 <= value <= 1.0


def test_load_reward_weights_overrides(tmp_path):
    config = tmp_path / "trace-mind.toml"
    config.write_text(
        """
        [reward_weights]
        outcome_ok = 0.9
        cost_usd = -0.5
        """.strip(),
        encoding="utf-8",
    )
    weights = load_reward_weights(config)
    assert pytest.approx(weights.outcome_ok, rel=1e-6) == 0.9
    assert weights.cost_usd == -0.5


def test_load_reward_weights_missing_file(tmp_path):
    path = tmp_path / "missing.toml"
    weights = load_reward_weights(path)
    assert weights == RewardWeights()
