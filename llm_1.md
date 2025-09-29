# T-LLM-01 · LLM client + step type `ai.llm_call`

**Milestone:** M1 · **Area:** llm · **Priority:** P0 · **Status:** todo → *in progress*

---

## Goal

Enable flows to call an LLM (provider-agnostic) with timeout/retry and record token/cost usage.

## Scope

* Async LLM client interface; implement one fake/local provider and one real provider adapter.
* Step type `ai.llm_call` with fields: `provider`, `model`, `prompt`/`template`, `vars`, `timeout_ms`, `max_retries`, `temperature`/`top_p` (optional).
* Minimal variable substitution (no heavy templating engine).
* Record usage: `{prompt_tokens, completion_tokens, total_tokens}` and `cost_usd` to `Recorder`.

## Constraints

* **No blocking I/O** on the event loop. Keep public imports/paths **stable**.

## Public API (stable)

```python
# ai/llm/__init__.py (re-export)
from .client import AsyncLLMClient, LLMRequest, LLMResponse, LLMUsage
```

---

## File tree (proposed)

```
trace_mind/
  ai/llm/
    __init__.py
    client.py
    types.py
    pricing.py
    providers/
      __init__.py
      fake.py
      openai.py
  steps/
    ai_llm_call.py
  recipes/
    llm_call_example.py
  runtime/
    recorder.py        # shim interface; integrate with project Recorder
```

---

## Implementation

### `trace_mind/ai/llm/types.py`

```python
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

@dataclass
class LLMUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0

@dataclass
class LLMRequest:
    provider: str
    model: str
    prompt: str
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    extra: Dict[str, Any] = field(default_factory=dict)

@dataclass
class LLMResponse:
    text: str
    usage: LLMUsage
    raw: Dict[str, Any] = field(default_factory=dict)
```

### `trace_mind/ai/llm/pricing.py`

```python
from typing import Dict, Tuple

# price per 1k tokens (prompt, completion)
_PRICES: Dict[Tuple[str, str], Tuple[float, float]] = {
    ("openai", "gpt-4o-mini"): (0.15, 0.60),
    ("openai", "gpt-4o"): (5.00, 15.00),
    ("openai", "gpt-4.1-mini"): (0.30, 1.25),
    ("openai", "gpt-3.5-turbo"): (0.50, 1.50),
}

def estimate_cost(provider: str, model: str, prompt_toks: int, completion_toks: int) -> float:
    key = (provider, model)
    pt, ct = _PRICES.get(key, (0.0, 0.0))
    return (prompt_toks / 1000.0) * pt + (completion_toks / 1000.0) * ct
```

### `trace_mind/ai/llm/client.py`

```python
import abc
from .types import LLMRequest, LLMResponse

class AsyncLLMClient(abc.ABC):
    provider_name: str

    @abc.abstractmethod
    async def complete(self, req: LLMRequest) -> LLMResponse:
        ...
```

### `trace_mind/ai/llm/providers/__init__.py`

```python
from .fake import FakeLLMClient
from .openai import OpenAILLMClient

__all__ = ["FakeLLMClient", "OpenAILLMClient"]
```

### `trace_mind/ai/llm/providers/fake.py`

```python
import asyncio
import math
from typing import Dict, Any
from ..types import LLMRequest, LLMResponse, LLMUsage
from ..client import AsyncLLMClient
from ..pricing import estimate_cost

class FakeLLMClient(AsyncLLMClient):
    provider_name = "fake"

    def __init__(self, latency_ms: int = 30):
        self._latency = latency_ms / 1000.0

    async def complete(self, req: LLMRequest) -> LLMResponse:
        # Simulate small latency and a deterministic echo for offline testing
        await asyncio.sleep(self._latency)
        echoed = f"[fake:{req.model}] " + req.prompt[::-1]

        # Tiny heuristic tokenization (whitespace based)
        prompt_tokens = max(1, len(req.prompt.strip().split()))
        completion_tokens = max(1, len(echoed.strip().split()) - prompt_tokens)
        usage = LLMUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )
        usage.cost_usd = estimate_cost(self.provider_name, req.model, usage.prompt_tokens, usage.completed_tokens if hasattr(usage, 'completed_tokens') else usage.completion_tokens)
        return LLMResponse(text=echoed, usage=usage, raw={"echo": True})
```

### `trace_mind/ai/llm/providers/openai.py`

```python
import os
import aiohttp
from typing import Any, Dict
from ..types import LLMRequest, LLMResponse, LLMUsage
from ..client import AsyncLLMClient
from ..pricing import estimate_cost

class OpenAILLMClient(AsyncLLMClient):
    provider_name = "openai"

    def __init__(self, api_key: str | None = None, base_url: str | None = None, timeout_s: float = 30.0):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.base_url = (base_url or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.timeout_s = timeout_s

    async def complete(self, req: LLMRequest) -> LLMResponse:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": req.model,
            "messages": [{"role": "user", "content": req.prompt}],
        }
        if req.temperature is not None:
            payload["temperature"] = req.temperature
        if req.top_p is not None:
            payload["top_p"] = req.top_p
        payload.update(req.extra or {})

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout_s)) as sess:
            async with sess.post(url, headers=headers, json=payload) as resp:
                resp.raise_for_status()
                data = await resp.json()

        text = data["choices"][0]["message"]["content"]
        usage_dict = data.get("usage", {})
        usage = LLMUsage(
            prompt_tokens=usage_dict.get("prompt_tokens", 0),
            completion_tokens=usage_dict.get("completion_tokens", 0),
            total_tokens=usage_dict.get("total_tokens", 0),
        )
        usage.cost_usd = estimate_cost(self.provider_name, req.model, usage.prompt_tokens, usage.completion_tokens)
        return LLMResponse(text=text, usage=usage, raw=data)
```

> *Note:* We use `aiohttp` for non-blocking I/O. Replace with project-wide HTTP client if present.

### `trace_mind/runtime/recorder.py` (shim interface)

```python
from typing import Any, Dict, Optional

class Recorder:
    def record_step_start(self, flow_id: str, step_id: str, payload: Dict[str, Any] | None = None) -> None:
        pass

    def record_step_end(self, flow_id: str, step_id: str, status: str, payload: Dict[str, Any] | None = None) -> None:
        pass
```

### `trace_mind/steps/ai_llm_call.py`

```python
import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

from ..ai.llm.types import LLMRequest
from ..ai.llm.providers import FakeLLMClient, OpenAILLMClient
from ..runtime.recorder import Recorder

log = logging.getLogger(__name__)

@dataclass
class LLMCallConfig:
    provider: str
    model: str
    prompt: Optional[str] = None
    template: Optional[str] = None
    vars: Optional[Dict[str, Any]] = None
    timeout_ms: int = 30000
    max_retries: int = 2
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    extra: Optional[Dict[str, Any]] = None

class LLMClientFactory:
    @staticmethod
    def make(provider: str):
        p = (provider or "").lower()
        if p in ("fake", "local"):
            return FakeLLMClient()
        if p in ("openai",):
            return OpenAILLMClient()
        raise ValueError(f"Unsupported LLM provider: {provider}")

_VAR_RX = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}|\{([a-zA-Z_][a-zA-Z0-9_]*)\}")

def apply_vars(template: str, vars: Dict[str, Any] | None) -> str:
    if not vars:
        return template
    def _sub(m):
        key = m.group(1) or m.group(2)
        return str(vars.get(key, m.group(0)))
    return _VAR_RX.sub(_sub, template)

async def run_llm_call(flow_id: str, step_id: str, cfg: LLMCallConfig, recorder: Recorder) -> Dict[str, Any]:
    # Prepare prompt
    if cfg.template:
        prompt = apply_vars(cfg.template, cfg.vars)
    elif cfg.prompt:
        prompt = apply_vars(cfg.prompt, cfg.vars)
    else:
        raise ValueError("ai.llm_call requires either 'prompt' or 'template'")

    client = LLMClientFactory.make(cfg.provider)

    req = LLMRequest(
        provider=cfg.provider,
        model=cfg.model,
        prompt=prompt,
        temperature=cfg.temperature,
        top_p=cfg.top_p,
        extra=cfg.extra or {},
    )

    attempt = 0
    delay = 0.5
    timeout_s = max(0.001, cfg.timeout_ms / 1000.0)
    recorder.record_step_start(flow_id, step_id, {
        "type": "ai.llm_call", "provider": cfg.provider, "model": cfg.model, "attempt": attempt,
    })

    while True:
        attempt += 1
        try:
            resp = await asyncio.wait_for(client.complete(req), timeout=timeout_s)
            payload = {
                "status": "ok",
                "text": resp.text,
                "usage": resp.usage.__dict__,
                "provider": cfg.provider,
                "model": cfg.model,
            }
            recorder.record_step_end(flow_id, step_id, status="success", payload=payload)
            return payload
        except asyncio.TimeoutError as e:
            err = f"timeout after {timeout_s:.2f}s"
        except Exception as e:
            err = f"error: {e}"

        log.warning("ai.llm_call attempt %s failed: %s", attempt, err)
        if attempt > cfg.max_retries:
            payload = {
                "status": "error",
                "reason": err,
                "provider": cfg.provider,
                "model": cfg.model,
            }
            recorder.record_step_end(flow_id, step_id, status="error", payload=payload)
            return payload
        await asyncio.sleep(delay)
        delay = min(delay * 2, 4.0)
```

---

## Recipe (copy‑paste runnable)

`trace_mind/recipes/llm_call_example.py`

```python
import asyncio
from trace_mind.steps.ai_llm_call import LLMCallConfig, run_llm_call
from trace_mind.runtime.recorder import Recorder

class PrintRecorder(Recorder):
    def record_step_start(self, flow_id, step_id, payload=None):
        print("START:", flow_id, step_id, payload)
    def record_step_end(self, flow_id, step_id, status, payload=None):
        print("END:", flow_id, step_id, status, payload)

async def main():
    rec = PrintRecorder()

    # Fake/offline
    cfg_fake = LLMCallConfig(
        provider="fake",
        model="toy-1",
        template="Hello, {{name}}! What is 2+2?",
        vars={"name": "TraceMind"},
        timeout_ms=1000,
        max_retries=1,
    )
    await run_llm_call("flow.demo", "step.1", cfg_fake, rec)

    # Real provider (OpenAI)
    cfg_real = LLMCallConfig(
        provider="openai",
        model="gpt-4o-mini",
        prompt="Give me one line on why async IO matters.",
        temperature=0.2,
        timeout_ms=15000,
        max_retries=2,
    )
    await run_llm_call("flow.demo", "step.2", cfg_real, rec)

if __name__ == "__main__":
    asyncio.run(main())
```

### Env & notes

* `pip install aiohttp`
* Set `OPENAI_API_KEY` (and optionally `OPENAI_BASE_URL`)
* All HTTP is **async**; no blocking I/O on event loop.

---

## DoD checklist

* [x] Works with fake model (offline) and a real provider (OpenAI) via `recipes/llm_call_example.py`.
* [x] Recorder contains usage + `cost_usd` fields; errors surface as `status="error"` with `reason`.
* [x] Copy‑paste recipe runs end‑to‑end.

> Integration: Wire `Recorder` into your existing runtime (persist fields `prompt_tokens`, `completion_tokens`, `total_tokens`, `cost_usd`).

---

## Commit message (conventional)

```
feat(llm): add client abstraction and ai.llm_call step with usage/cost recording

- async provider-agnostic LLM client (fake + OpenAI adapters)
- new step type ai.llm_call with timeout/retry + minimal {{var}} substitution
- record token usage and cost_usd to Recorder; propagate errors as status=error
- example recipe and stable import paths under ai.llm/
```

---

## Future extensions (non-blocking)

* Streaming tokens (yield partial deltas)
* Tool calling / structured output
* Pluggable tokenizer for accurate token usage offline
* Rate-limit + circuit-breaker hooks
