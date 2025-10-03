import math
import pytest

from tm.ai.retrospect import Retrospect
from tm.ai.run_pipeline import RewardWeights, RunEndPipeline
from tm.ai.tuner import BanditTuner
from tm.flow.runtime import FlowRunRecord
from tm.obs import counters
from tm.obs.recorder import Recorder


def _reset_metrics() -> None:
    counters.metrics.reset()
    Recorder._default = None  # type: ignore[attr-defined]


def _make_record(binding: str, arm: str, *, good: bool, seq: int) -> FlowRunRecord:
    duration = 40.0 if good else 300.0
    cost = 0.02 if good else 1.5
    rating = 0.9 if good else 0.1
    task_success = 1.0 if good else 0.0
    start_ts = seq * 10.0
    end_ts = start_ts + (duration / 1000.0)
    return FlowRunRecord(
        flow=arm,
        flow_id=arm,
        flow_rev="rev-1",
        run_id=f"run-{seq}-{arm}",
        selected_flow=arm,
        binding=binding,
        status="ok",
        outcome="ok",
        queued_ms=0.0,
        exec_ms=duration,
        duration_ms=duration,
        start_ts=start_ts,
        end_ts=end_ts,
        cost_usd=cost,
        user_rating=rating,
        reward=None,
        meta={"task_success": task_success},
    )


@pytest.mark.asyncio
async def test_closed_loop_prefers_better_arm():
    _reset_metrics()
    tuner = BanditTuner(strategy="epsilon", epsilon=0.2)
    retro = Retrospect(window_seconds=60.0)
    pipeline = RunEndPipeline(retro, tuner, weights=RewardWeights())

    binding = "demo:read"
    arms = ["flow_fast", "flow_slow"]
    counts = {arm: 0 for arm in arms}

    total_rounds = 80
    for idx in range(total_rounds):
        choice = await tuner.choose(binding, arms)
        counts[choice] += 1
        good = choice == "flow_fast"
        record = _make_record(binding, choice, good=good, seq=idx)
        await pipeline.on_run_end(record)

    assert counts["flow_fast"] > counts["flow_slow"]

    select_samples = counters.metrics.get_counter("tm_tuner_select_total").samples()
    labels_to_value = {tuple(sorted(lbl)): value for lbl, value in select_samples}
    fast_key = tuple(sorted((("arm", "flow_fast"), ("flow", binding))))
    slow_key = tuple(sorted((("arm", "flow_slow"), ("flow", binding))))
    assert fast_key in labels_to_value
    assert labels_to_value[fast_key] == pytest.approx(counts["flow_fast"], rel=1e-6)

    reward_samples = counters.metrics.get_gauge("tm_tuner_reward_sum").samples()
    reward_lookup = {tuple(sorted(lbl)): value for lbl, value in reward_samples}
    fast_reward = reward_lookup[fast_key]
    slow_reward = reward_lookup[slow_key]
    assert fast_reward > slow_reward
