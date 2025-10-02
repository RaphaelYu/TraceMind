import pytest

from tm.ai.feedback import FeedbackEvent, reward
from tm.ai.retrospect import Retrospect
from tm.ai.run_pipeline import RewardWeights, RunEndPipeline
from tm.ai.tuner import BanditTuner
from tm.flow.runtime import FlowRunRecord


@pytest.mark.asyncio
async def test_run_end_pipeline_updates_components():
    retro = Retrospect(window_seconds=30.0)
    tuner = BanditTuner(strategy="epsilon", epsilon=0.5)
    weights = RewardWeights(outcome_ok=0.8, user_rating=0.5, latency_ms=0.0, cost_usd=0.0, task_success=0.0)
    pipeline = RunEndPipeline(retro, tuner, weights=weights)

    record = FlowRunRecord(
        flow="demo-flow",
        flow_id="demo-flow",
        flow_rev="rev-1",
        run_id="run-1",
        selected_flow="arm-a",
        binding="demo:read",
        status="ok",
        outcome="ok",
        queued_ms=5.0,
        exec_ms=12.0,
        duration_ms=18.0,
        start_ts=0.0,
        end_ts=0.018,
        cost_usd=None,
        user_rating=0.8,
        reward=None,
        meta={},
    )

    await pipeline.on_run_end(record)

    summary = retro.summary("demo:read")["demo:read"]
    assert summary.n == 1
    expected = reward(
        FeedbackEvent(
            outcome="ok",
            duration_ms=record.duration_ms,
            cost_usd=record.cost_usd,
            user_rating=record.user_rating,
        ),
        weights,
    )
    assert pytest.approx(summary.avg_reward, rel=1e-6) == expected
    stats = await tuner.stats("demo:read")
    assert stats["arm-a"]["pulls"] == 1
    assert pytest.approx(record.reward, rel=1e-6) == expected
