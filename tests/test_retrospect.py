from tm.ai.retrospect import Retrospect
from tm.flow.runtime import FlowRunRecord


def _record(binding: str, *, status: str, reward: float, end_ts: float, latency: float) -> FlowRunRecord:
    return FlowRunRecord(
        flow="flow-x",
        flow_id="flow-x",
        flow_rev="rev-1",
        run_id=f"run-{end_ts}",
        selected_flow="flow-x",
        binding=binding,
        status=status,
        outcome=status,
        queued_ms=0.0,
        exec_ms=latency,
        duration_ms=latency,
        start_ts=end_ts - (latency / 1000.0),
        end_ts=end_ts,
        cost_usd=None,
        user_rating=None,
        reward=reward,
        meta={},
    )


def test_retrospect_window_metrics():
    retro = Retrospect(window_seconds=10.0)
    retro.ingest(_record("demo:read", status="ok", reward=1.0, end_ts=5.0, latency=20.0))
    retro.ingest(_record("demo:read", status="error", reward=-1.0, end_ts=6.0, latency=30.0))
    summary = retro.summary("demo:read")["demo:read"]
    assert summary.count == 2
    assert summary.ok_rate == 0.5
    assert summary.avg_reward == 0.0
    assert summary.avg_latency_ms == 25.0

    # Record outside the window should be dropped
    retro.ingest(_record("demo:read", status="ok", reward=2.0, end_ts=20.0, latency=40.0))
    summary = retro.summary("demo:read")["demo:read"]
    assert summary.count == 1
    assert summary.ok_rate == 1.0
    assert summary.avg_reward == 2.0
