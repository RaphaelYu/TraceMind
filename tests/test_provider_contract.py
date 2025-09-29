import pytest
from tm.ai.providers.fake import FakeProvider
from tm.ai.providers.base import Provider, LlmCallResult

@pytest.mark.asyncio
async def test_fake_provider_contract():
    p: Provider = FakeProvider()
    res: LlmCallResult = await p.complete(model="fake-mini", prompt="hello")
    assert isinstance(res.output_text, str)
    assert res.usage.total_tokens >= res.usage.prompt_tokens + res.usage.completion_tokens
