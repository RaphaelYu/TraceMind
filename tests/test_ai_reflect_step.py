import json
import pytest

from tm.ai.providers.base import LlmCallResult, LlmUsage
from tm.obs import counters
from tm.obs.recorder import Recorder

from tm.steps.ai_reflect import run as reflect_step


class StubClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    async def call(self, **kwargs):
        if self.calls >= len(self._responses):
            raise AssertionError("No more responses")
        resp = self._responses[self.calls]
        self.calls += 1
        return resp


@pytest.fixture(autouse=True)
def reset_metrics():
    counters.metrics._counters.clear()
    counters.metrics._gauges.clear()
    Recorder._default = None  # type: ignore[attr-defined]


def make_stub(responses):
    client = StubClient([])
    client._responses = responses
    return client


@pytest.mark.asyncio
async def test_ai_reflect_success(monkeypatch):
    reflection_payload = {
        "version": "reflect.v1",
        "summary": "Worked",
        "issues": ["none"],
        "guidance": "Proceed",
        "plan_patch": {
            "ops": [
                {"op": "replace", "path": "/steps/0/inputs/value", "value": 42}
            ]
        },
        "policy_update": {},
    }
    responses = [
        LlmCallResult(
            output_text=json.dumps(reflection_payload),
            usage=LlmUsage(prompt_tokens=5, completion_tokens=5, total_tokens=10, cost_usd=0.01),
        )
    ]
    monkeypatch.setattr("tm.steps.ai_reflect.make_client", lambda provider: make_stub(responses))

    result = await reflect_step({
        "provider": "fake",
        "model": "reflector",
        "recent_outcomes": {"last": "ok"},
        "retrospect_stats": {},
    })
    assert result["status"] == "ok"
    assert result["reflection"]["summary"] == "Worked"
    assert counters.metrics.get_counter("tm_reflect_requests_total").samples()[0][1] == 1.0


@pytest.mark.asyncio
async def test_ai_reflect_invalid_json(monkeypatch):
    responses = [
        LlmCallResult(
            output_text="bad",
            usage=LlmUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2, cost_usd=0.0),
        )
    ]
    monkeypatch.setattr("tm.steps.ai_reflect.make_client", lambda provider: make_stub(responses))

    result = await reflect_step({
        "provider": "fake",
        "model": "reflector",
        "recent_outcomes": {},
        "retrospect_stats": {},
    })
    assert result["status"] == "error"
    assert result["error_code"] == "GUARD_BLOCKED"
    assert counters.metrics.get_counter("tm_reflect_failures_total").samples()[0][1] == 1.0


@pytest.mark.asyncio
async def test_ai_reflect_retries_then_succeeds(monkeypatch):
    good_payload = {
        "summary": "Patched",
        "issues": [],
        "policy_update": {},
    }
    responses = [
        LlmCallResult(
            output_text="not json",
            usage=LlmUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        ),
        LlmCallResult(
            output_text=json.dumps(good_payload),
            usage=LlmUsage(prompt_tokens=2, completion_tokens=2, total_tokens=4),
        ),
    ]
    monkeypatch.setattr("tm.steps.ai_reflect.make_client", lambda provider: make_stub(responses))

    result = await reflect_step({
        "provider": "fake",
        "model": "reflector",
        "recent_outcomes": {},
        "retrospect_stats": {},
        "retries": 1,
        "retry_backoff_ms": 0,
    })
    assert result["status"] == "ok"
    assert result["retries"] == 1


@pytest.mark.asyncio
async def test_ai_reflect_rejects_invalid_patch(monkeypatch):
    payload = {
        "summary": "Bad patch",
        "issues": [],
        "plan_patch": {"ops": [{"op": "replace", "path": "/plan/0", "value": 1}]},
        "policy_update": {},
    }
    responses = [
        LlmCallResult(
            output_text=json.dumps(payload),
            usage=LlmUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )
    ]
    monkeypatch.setattr("tm.steps.ai_reflect.make_client", lambda provider: make_stub(responses))

    result = await reflect_step({
        "provider": "fake",
        "model": "reflector",
        "recent_outcomes": {},
        "retrospect_stats": {},
    })
    assert result["status"] == "error"
    assert result["error_code"] == "GUARD_BLOCKED"
