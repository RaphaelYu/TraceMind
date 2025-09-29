### ai.llm_call (FakeProvider, runnable)

```python
import asyncio
from tm.steps.ai_llm_call import run

params = {
  "provider": "fake",
  "model": "fake-mini",
  "template": "Hello, {{name}}!",
  "vars": {"name": "Ruifei"},
  "timeout_ms": 5000,
}

print(asyncio.run(run(params)))
```

### Retry + timeout
```python
import asyncio
from tm.steps.ai_llm_call import run

params = {
  "provider": "fake",
  "model": "fake-mini",
  "prompt": "ping",
  "timeout_ms": 1,
  "max_retries": 1,
}
print(asyncio.run(run(params)))
```
