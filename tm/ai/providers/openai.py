from __future__ import annotations
import dataclasses
from typing import Optional, Protocol, Mapping, Any
from .base import Provider, LlmCallResult, LlmUsage, LlmError


@dataclasses.dataclass
class Pricing:
    in_per_million: float
    out_per_million: float


class _AsyncTransport(Protocol):
    async def post(self, *, url: str, headers: Mapping[str, str], json: Mapping[str, Any]) -> dict: ...


_DEFAULT_PRICING: dict[str, Pricing] = {
    # Example only; adjust outside if needed
    "gpt-4o-mini": Pricing(0.150, 0.600),
}


class OpenAIProvider(Provider):
    """Structure-complete provider with pluggable async transport.

    By default it does *not* perform real network I/O unless a transport is provided.
    """

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        pricing: Optional[dict[str, Pricing]] = None,
        transport: Optional[_AsyncTransport] = None,
    ):
        self.api_key = api_key or ""
        self.base_url = (base_url or "https://api.openai.com/v1/chat/completions").rstrip("/")
        self.pricing = pricing or _DEFAULT_PRICING
        self._transport = transport  # may be None → raises at call time

    async def complete(
        self,
        *,
        model: str,
        prompt: str,
        temperature: float | None = None,
        top_p: float | None = None,
        timeout_s: float | None = None,
    ) -> LlmCallResult:
        if self._transport is None:
            raise LlmError("PROVIDER_ERROR", "No transport configured for OpenAIProvider")

        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        }
        if temperature is not None:
            payload["temperature"] = float(temperature)
        if top_p is not None:
            payload["top_p"] = float(top_p)

        try:
            data = await self._transport.post(url=self.base_url, headers=headers, json=payload)
        except Exception as e:  # map network failures uniformly
            raise LlmError("PROVIDER_ERROR", f"transport error: {e}")

        # expected OpenAI-ish shape
        try:
            choice = data["choices"][0]
            text = choice.get("message", {}).get("content", "")
            usage_blob = data.get("usage", {})
            pt = int(usage_blob.get("prompt_tokens", 0) or 0)
            ct = int(usage_blob.get("completion_tokens", 0) or 0)
            tt = int(usage_blob.get("total_tokens", pt + ct) or (pt + ct))
        except Exception as e:
            raise LlmError("PROVIDER_ERROR", f"unexpected response shape: {e}")

        price = self.pricing.get(model)
        cost = None
        if price is not None:
            cost = (pt * price.in_per_million + ct * price.out_per_million) / 1_000_000.0

        usage = LlmUsage(prompt_tokens=pt, completion_tokens=ct, total_tokens=tt, cost_usd=cost)
        return LlmCallResult(output_text=text, usage=usage, raw=data)
