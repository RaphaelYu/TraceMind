from __future__ import annotations
import asyncio
import os
from .base import Provider, LlmCallResult, LlmUsage


class FakeProvider(Provider):
    """Deterministic, offline provider for tests and local runs."""

    def __init__(self, *, delay_ms: int | None = None):
        self._delay_ms = delay_ms if delay_ms is not None else int(os.getenv("FAKE_DELAY_MS", "0") or 0)

    async def complete(
        self,
        *,
        model: str,
        prompt: str,
        temperature: float | None = None,
        top_p: float | None = None,
        timeout_s: float | None = None,
    ) -> LlmCallResult:
        # simulate minimal latency (cooperative)
        if self._delay_ms > 0:
            await asyncio.sleep(self._delay_ms / 1000.0)
        # synthetic output
        text = f"echo[{model}]: " + prompt
        # super-naive token counts; roughly 4 chars/token
        pt = max(1, len(prompt) // 4)
        ct = max(1, len(text) // 4)
        usage = LlmUsage(prompt_tokens=pt, completion_tokens=ct, total_tokens=pt + ct, cost_usd=0.0)
        return LlmCallResult(output_text=text, usage=usage, raw={"provider": "fake"})
