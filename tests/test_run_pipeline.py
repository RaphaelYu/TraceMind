import pytest

from tm.ai.retrospect import Retrospect
from tm.ai.run_pipeline import RewardWeights, RunEndPipeline
from tm.ai.tuner import BanditTuner
from tm.flow.runtime import FlowRunRecord


@pytest.mark.asyncio
async def test_run_end_pipeline_updates_components():
    retro = Retrospect(window_seconds=30.0)
    tuner = BanditTuner(alpha=0.5, exploration_bonus=0.0)
    pipeline = RunEndPipeline(retro, tuner, weights=RewardWeights(success=1.0, user_rating=0.5))

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
    assert summary.count == 1
    expected_reward = 1.0 + 0.5 * 0.8
    assert pytest.approx(summary.avg_reward, rel=1e-6) == expected_reward
    stats = await tuner.stats("demo:read")
    assert stats["arm-a"]["updates"] == 1.0
    assert pytest.approx(record.reward, rel=1e-6) == expected_reward
*** End of File ***
