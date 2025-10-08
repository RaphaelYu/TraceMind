from __future__ import annotations
import asyncio
from .providers.base import Provider, LlmCallResult, LlmError
from .providers.fake import FakeProvider
from .providers.openai import OpenAIProvider
from tm.utils.async_tools import with_timeout, with_retry


class AsyncLLMClient:
    def __init__(self, provider: Provider):
        self._provider = provider

    async def call(
        self,
        *,
        model: str,
        prompt: str,
        temperature: float | None = None,
        top_p: float | None = None,
        timeout_ms: int | None = None,
        max_retries: int = 0,
    ) -> LlmCallResult:
        timeout_s = (timeout_ms / 1000.0) if (timeout_ms and timeout_ms > 0) else None

        def _is_retryable(e: Exception) -> bool:
            code = getattr(e, "code", None)
            return code in {"RATE_LIMIT", "PROVIDER_ERROR", "RUN_TIMEOUT"}

        async def _once() -> LlmCallResult:
            try:
                return await with_timeout(
                    self._provider.complete(
                        model=model,
                        prompt=prompt,
                        temperature=temperature,
                        top_p=top_p,
                        timeout_s=timeout_s,
                    ),
                    timeout_s=timeout_s,
                )
            except asyncio.CancelledError:
                raise LlmError("RUN_CANCELLED", "task cancelled")

        return await with_retry(_once, max_retries=max_retries, is_retryable=_is_retryable)


def make_client(provider_name: str, **kwargs) -> AsyncLLMClient:
    name = provider_name.lower().strip()
    if name == "fake":
        prov: Provider = FakeProvider(**kwargs)
    elif name == "openai":
        prov = OpenAIProvider(**kwargs)
    else:
        raise ValueError(f"unknown provider: {provider_name}")
    return AsyncLLMClient(prov)
