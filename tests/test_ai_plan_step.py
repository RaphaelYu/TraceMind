import json
import pytest

from tm.ai.providers.base import LlmCallResult, LlmUsage
from tm.obs import counters
from tm.obs.recorder import Recorder

from tm.steps.ai_plan import run as plan_step


class StubClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    async def call(self, **kwargs):
        if self.calls >= len(self._responses):
            raise AssertionError("No more stub responses")
        resp = self._responses[self.calls]
        self.calls += 1
        return resp


def _reset_metrics():
    counters.metrics.reset()


@pytest.mark.asyncio
async def test_ai_plan_generates_valid_plan(monkeypatch):
    _reset_metrics()
    Recorder._default = None  # type: ignore[attr-defined]

    plan_payload = {
        "version": "plan.v1",
        "goal": "Sort numbers",
        "constraints": {"max_steps": 5},
        "allow": {"tools": ["tool.sort"], "flows": []},
        "steps": [
            {
                "id": "s1",
                "kind": "tool",
                "ref": "tool.sort",
                "inputs": {"items": [3, 2, 1]},
            }
        ],
    }

    responses = [
        LlmCallResult(
            output_text=json.dumps(plan_payload),
            usage=LlmUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30, cost_usd=0.01),
        )
    ]
    monkeypatch.setattr("tm.steps.ai_plan.make_client", lambda provider: StubClient(responses))

    result = await plan_step(
        {
            "provider": "fake",
            "model": "planner",
            "goal": "Sort numbers",
            "allow": {"tools": ["tool.sort"], "flows": []},
            "constraints": {"max_steps": 5},
        }
    )

    assert result["status"] == "ok"
    assert result["plan"]["goal"] == "Sort numbers"
    assert result["plan"]["steps"][0]["ref"] == "tool.sort"

    request_samples = counters.metrics.get_counter("tm_plan_requests_total").samples()
    assert request_samples[0][1] == 1.0
    assert not counters.metrics.get_counter("tm_plan_failures_total").samples()


@pytest.mark.asyncio
async def test_ai_plan_handles_invalid_json(monkeypatch):
    _reset_metrics()
    Recorder._default = None  # type: ignore[attr-defined]

    responses = [
        LlmCallResult(
            output_text="not json",
            usage=LlmUsage(prompt_tokens=5, completion_tokens=5, total_tokens=10, cost_usd=0.0),
        )
    ]
    monkeypatch.setattr("tm.steps.ai_plan.make_client", lambda provider: StubClient(responses))

    result = await plan_step(
        {
            "provider": "fake",
            "model": "planner",
            "goal": "Do work",
            "allow": {"tools": ["tool.sort"], "flows": []},
        }
    )

    assert result["status"] == "error"
    assert result["error_code"] == "GUARD_BLOCKED"
    failures = counters.metrics.get_counter("tm_plan_failures_total").samples()
    assert failures[0][1] == 1.0


@pytest.mark.asyncio
async def test_ai_plan_retries_and_succeeds(monkeypatch):
    _reset_metrics()
    Recorder._default = None  # type: ignore[attr-defined]

    valid_plan = {
        "version": "plan.v1",
        "goal": "Sort numbers",
        "constraints": {},
        "allow": {"tools": ["tool.sort"], "flows": []},
        "steps": [
            {
                "id": "s1",
                "kind": "tool",
                "ref": "tool.sort",
                "inputs": {"items": [3, 2, 1]},
            }
        ],
    }

    responses = [
        LlmCallResult(
            output_text="oops",
            usage=LlmUsage(prompt_tokens=5, completion_tokens=5, total_tokens=10, cost_usd=0.0),
        ),
        LlmCallResult(
            output_text=json.dumps(valid_plan),
            usage=LlmUsage(prompt_tokens=10, completion_tokens=15, total_tokens=25, cost_usd=0.02),
        ),
    ]
    monkeypatch.setattr("tm.steps.ai_plan.make_client", lambda provider: StubClient(responses))

    result = await plan_step(
        {
            "provider": "fake",
            "model": "planner",
            "goal": "Sort numbers",
            "allow": {"tools": ["tool.sort"], "flows": []},
            "retries": 1,
            "retry_backoff_ms": 0,
        }
    )

    assert result["status"] == "ok"
    assert result["retries"] == 1
    retry_counter = counters.metrics.get_counter("tm_plan_retries_total").samples()
    assert retry_counter[0][1] == 1.0


@pytest.mark.asyncio
async def test_ai_plan_rejects_disallowed_refs(monkeypatch):
    _reset_metrics()
    Recorder._default = None  # type: ignore[attr-defined]

    bad_plan = {
        "version": "plan.v1",
        "goal": "Sort numbers",
        "constraints": {},
        "allow": {"tools": ["tool.other"], "flows": []},
        "steps": [
            {
                "id": "s1",
                "kind": "tool",
                "ref": "tool.other",
                "inputs": {},
            }
        ],
    }

    responses = [
        LlmCallResult(
            output_text=json.dumps(bad_plan),
            usage=LlmUsage(prompt_tokens=5, completion_tokens=5, total_tokens=10, cost_usd=0.0),
        )
    ]
    monkeypatch.setattr("tm.steps.ai_plan.make_client", lambda provider: StubClient(responses))

    result = await plan_step(
        {
            "provider": "fake",
            "model": "planner",
            "goal": "Sort numbers",
            "allow": {"tools": ["tool.sort"], "flows": []},
        }
    )

    assert result["status"] == "error"
    assert result["error_code"] == "POLICY_FORBIDDEN"
