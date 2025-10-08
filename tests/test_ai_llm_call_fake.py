import pytest
from tm.steps.ai_llm_call import run


@pytest.mark.asyncio
async def test_ok_with_template():
    out = await run(
        {"provider": "fake", "model": "fake-mini", "template": "Hello, {{name}}", "vars": {"name": "Ruifei"}}
    )
    assert out["status"] == "ok"
    assert "Ruifei" in out["text"]


@pytest.mark.asyncio
async def test_missing_var():
    out = await run({"provider": "fake", "model": "fake-mini", "template": "Hello, {{name}}", "vars": {}})
    assert out["status"] == "error"
    assert out["code"] == "BAD_REQUEST"


@pytest.mark.asyncio
async def test_timeout_error(monkeypatch):
    monkeypatch.setenv("FAKE_DELAY_MS", "50")
    # Set a very short timeout to trigger timeout error
    out = await run(
        {
            "provider": "fake",
            "model": "fake-mini",
            "prompt": "ping",
            "timeout_ms": 1,  # very short timeout
            "max_retries": 0,
        }
    )
    assert out["status"] == "error"
    assert out["code"] in ("RUN_TIMEOUT", "PROVIDER_ERROR")
