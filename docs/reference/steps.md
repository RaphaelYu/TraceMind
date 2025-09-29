# Step Types

## ai.llm_call
See: How-to › LLM Call

Inputs:
- provider, model
- template + vars OR prompt
- timeout_ms, max_retries, temperature, top_p

Outputs:
- status, text, usage{prompt_tokens, completion_tokens, total_tokens, cost_usd}, provider, model
