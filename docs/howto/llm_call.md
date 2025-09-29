# How-to: Use `ai.llm_call`

## Parameters
- `provider` (str): e.g., `fake` or `openai`
- `model` (str)
- `template` (str) + `vars` (dict) **or** `prompt` (str)
- `timeout_ms` (int), `max_retries` (int)
- `temperature`, `top_p` (optional)

## Examples
- Template mode:
  ```yaml
  type: ai.llm_call
  with:
    provider: fake
    model: fake-mini
    template: "Hello, {{name}}"
    vars: { name: Alice }
  ```
- Prompt mode:
  ```yaml
  type: ai.llm_call
  with:
    provider: fake
    model: fake-mini
    prompt: "Say hi to Alice"
  ```

## Return shape
```json
{
  "status": "ok",
  "provider": "fake",
  "model": "fake-mini",
  "text": "...",
  "usage": {
    "prompt_tokens": 12,
    "completion_tokens": 24,
    "total_tokens": 36,
    "cost_usd": 0.0
  }
}
```

## Errors & retries
- Retries apply to: `RATE_LIMIT`, `PROVIDER_ERROR`, `RUN_TIMEOUT`
- No retry: `BAD_REQUEST`
- Cancellation: `RUN_CANCELLED`
